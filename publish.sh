#!/bin/bash

##############################################################################################
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
##############################################################################################

##############################################################################################
# Create new Cfn artifacts bucket if not already existing
# Build artifacts
# Upload artifacts to S3 bucket for deployment with CloudFormation
##############################################################################################

# Stop the publish process on failures
set -e

USAGE="$0 <cfn_bucket_basename> <cfn_prefix> <region> [public]"

# Check for required tools and dependencies
check_prerequisites() {
    local tools=("docker" "sam" "zip" "pip3" "npm")
    local min_sam_version="1.118.0"
    
    # Check if docker is installed
    if ! [ -x "$(command -v docker)" ]; then
        echo 'Error: docker is not installed and required.' >&2
        echo 'Install: https://docs.docker.com/engine/install/' >&2
        exit 1
    fi
    
    # Check if docker is running
    if ! docker ps &> /dev/null; then
        echo 'Error: docker is not running.' >&2
        exit 1
    fi
    
    # Check for required tools
    for tool in "${tools[@]}"; do
        if ! [ -x "$(command -v $tool)" ]; then
            echo "Error: $tool is not installed and required." >&2
            exit 1
        fi
    done
    
    # Check sam version
    sam_version=$(sam --version | awk '{print $4}')
    if [[ $(echo -e "$min_sam_version\n$sam_version" | sort -V | tail -n1) == $min_sam_version && $min_sam_version != $sam_version ]]; then
        echo "Error: sam version >= $min_sam_version is required. (Installed version is $sam_version)" >&2
        echo 'Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/manage-sam-cli-versions.html' >&2
        exit 1
    fi
    
    # Check for virtualenv
    if ! python3 -c "import virtualenv" 2>/dev/null; then
        echo 'Error: virtualenv python package is not installed and required.' >&2
        echo 'Run "pip3 install virtualenv"' >&2
        exit 1
    fi
    
    # Check node version
    if ! node -v | grep -qF "v18."; then
        echo 'Error: Node.js version 18.x is not installed and required.' >&2
        exit 1
    fi
}

# Parse command line arguments
parse_arguments() {
    BUCKET_BASENAME=$1
    [ -z "$BUCKET_BASENAME" ] && echo "Cfn bucket name is a required parameter. Usage $USAGE" && exit 1
    
    PREFIX=$2
    [ -z "$PREFIX" ] && echo "Prefix is a required parameter. Usage $USAGE" && exit 1
    
    REGION=$3
    [ -z "$REGION" ] && echo "Region is a required parameter. Usage $USAGE" && exit 1
    export AWS_DEFAULT_REGION=$REGION
    
    ACL=$4
    if [ "$ACL" == "public" ]; then
        echo "Published S3 artifacts will be accessible by public (read-only)"
        PUBLIC=true
    else
        echo "Published S3 artifacts will NOT be accessible by public."
        PUBLIC=false
    fi
    
    # Remove trailing slash from prefix if needed, and append VERSION
    VERSION=$(cat ./VERSION)
    [[ "${PREFIX}" == */ ]] && PREFIX="${PREFIX%?}"
    PREFIX_AND_VERSION=${PREFIX}/${VERSION}
    
    # Append region to bucket basename
    BUCKET=${BUCKET_BASENAME}-${REGION}
}

# Set up S3 bucket
setup_bucket() {
    # Create bucket if it doesn't already exist
    if [ -x $(aws s3api list-buckets --query 'Buckets[].Name' | grep "\"$BUCKET\"") ]; then
        echo "Creating s3 bucket: $BUCKET"
        aws s3 mb s3://${BUCKET} || exit 1
        aws s3api put-bucket-versioning --bucket ${BUCKET} --versioning-configuration Status=Enabled || exit 1
    else
        echo "Using existing bucket: $BUCKET"
    fi
    
    timestamp=$(date "+%Y%m%d_%H%M")
    tmpdir=/tmp/lma
    echo "Make temp dir: $tmpdir"
    [ -d $tmpdir ] && rm -fr $tmpdir
    mkdir -p $tmpdir
}

# Calculate hash for directories
calculate_hash() {
    local directory_path=$1
    local HASH=$(
        find "$directory_path" \( -name node_modules -o -name build \) -prune -o -type f -print0 | 
        sort -f -z |
        xargs -0 sha256sum |
        sha256sum |
        cut -d" " -f1 | 
        cut -c1-16
    )
    echo $HASH
}

# Check if directory has changed
haschanged() {
    local dir=$1
    local checksum_file="${dir}/.checksum"
    
    # Compute current checksum
    dir_checksum=$(find "$dir" -type d \( -name "python" -o -name "node_modules" -o -name "build" \) -prune -o -type f ! -name ".checksum" -exec stat --format='%Y' {} \; | sha256sum | awk '{ print $1 }')
    combined_string="$BUCKET $PREFIX_AND_VERSION $REGION $dir_checksum"
    current_checksum=$(echo -n "$combined_string" | sha256sum | awk '{ print $1 }')
    
    # Check if the checksum file exists and read the previous checksum
    if [ -f "$checksum_file" ]; then
        previous_checksum=$(cat "$checksum_file")
    else
        previous_checksum=""
    fi
    
    if [ "$current_checksum" != "$previous_checksum" ]; then
        return 0  # True, changed
    else
        return 1  # False, unchanged
    fi
}

# Update checksum for directory
update_checksum() {
    local dir=$1
    local checksum_file="${dir}/.checksum"
    
    # Compute current checksum
    dir_checksum=$(find "$dir" -type d \( -name "python" -o -name "node_modules" -o -name "build" \) -prune -o -type f ! -name ".checksum" -exec stat --format='%Y' {} \; | sha256sum | awk '{ print $1 }')
    combined_string="$BUCKET $PREFIX_AND_VERSION $REGION $dir_checksum"
    current_checksum=$(echo -n "$combined_string" | sha256sum | awk '{ print $1 }')
    
    # Save the current checksum
    echo "$current_checksum" > "$checksum_file"
}

# Check if submodule has changed
hassubmodulechanged() {
    local dir=$1
    local hash_file="${dir}/.commit-hash"
    
    # Get the current commit hash of the submodule
    cd "$dir" || exit 1
    current_hash=$(git rev-parse HEAD)
    cd - > /dev/null || exit 1
    
    # Check if the hash file exists and read the previous hash
    if [ -f "$hash_file" ]; then
        previous_hash=$(cat "$hash_file")
    else
        previous_hash=""
    fi
    
    if [ "$current_hash" != "$previous_hash" ]; then
        return 0  # True, changed
    else
        return 1  # False, unchanged
    fi
}

# Update submodule hash
update_submodule_hash() {
    local dir=$1
    local hash_file="${dir}/.commit-hash"
    
    # Get the current commit hash of the submodule
    cd "$dir" || exit 1
    current_hash=$(git rev-parse HEAD)
    cd - > /dev/null || exit 1
    
    # Save the current hash
    echo "$current_hash" > "$hash_file"
}

# Package a source directory as zip and upload to S3
package_source_zip() {
    local dir=$1
    local zipfile=$2
    local s3_path=$3
    
    echo "Zipping source to ${tmpdir}/${zipfile}"
    pushd $dir > /dev/null
    zip -r ${tmpdir}/${zipfile} . -x "node_modules/*" -x "build/*"
    popd > /dev/null
    
    echo "Upload source to S3: ${s3_path}"
    aws s3 cp ${tmpdir}/${zipfile} s3://${s3_path}
}

# Upload and validate CloudFormation template
upload_validate_template() {
    local source_path=$1
    local template_name=$2
    local s3_prefix=$3
    
    local s3_template="s3://${BUCKET}/${s3_prefix}/${template_name}"
    local https_template="https://s3.${REGION}.amazonaws.com/${BUCKET}/${s3_prefix}/${template_name}"
    
    echo "Uploading template to: ${s3_template}"
    aws s3 cp ${source_path} ${s3_template}
    
    echo "Validating template: ${https_template}"
    aws cloudformation validate-template --template-url ${https_template} > /dev/null || exit 1
}

# Package and upload a CloudFormation template
package_template() {
    local dir=$1
    local template_file=$2
    local s3_prefix=$3
    
    local s3_template="s3://${BUCKET}/${s3_prefix}/$(basename ${template_file})"
    local https_template="https://s3.${REGION}.amazonaws.com/${BUCKET}/${s3_prefix}/$(basename ${template_file})"
    
    aws cloudformation package \
    --template-file ${template_file} \
    --output-template-file ${tmpdir}/$(basename ${template_file}) \
    --s3-bucket $BUCKET --s3-prefix ${s3_prefix} \
    --region ${REGION} || exit 1
    
    echo "Uploading template to: ${s3_template}"
    aws s3 cp ${tmpdir}/$(basename ${template_file}) ${s3_template}
    
    echo "Validating template"
    aws cloudformation validate-template --template-url ${https_template} > /dev/null || exit 1
}

# Process browser extension stack
process_browser_extension() {
    local dir="lma-browser-extension-stack"
    echo "Processing ${dir}"
    
    # Hash the contents to create unique filename
    pushd ${dir} > /dev/null
    echo "Computing hash of extension folder contents"
    local hash=$(calculate_hash ".")
    local zipfile="src-${hash}.zip"
    BROWSER_EXTENSION_SRC_S3_LOCATION="${BUCKET}/${PREFIX_AND_VERSION}/${dir}/${zipfile}"
    popd > /dev/null
    
    if haschanged ${dir}; then
        echo "PACKAGING ${dir}"
        package_source_zip ${dir} ${zipfile} "${BROWSER_EXTENSION_SRC_S3_LOCATION}"
        upload_validate_template "${dir}/template.yaml" "template.yaml" "${PREFIX_AND_VERSION}/${dir}"
        update_checksum ${dir}
    else
        echo "SKIPPING ${dir} (unchanged)"
    fi
}

# Process virtual participant stack
process_virtual_participant() {
    local dir="lma-virtual-participant-stack"
    echo "Processing ${dir}"
    
    pushd ${dir} > /dev/null
    echo "Computing hash of extension folder contents"
    local hash=$(calculate_hash ".")
    local zipfile="src-${hash}.zip"
    popd > /dev/null
    
    echo "PACKAGING ${dir}"
    package_source_zip ${dir} ${zipfile} "${BUCKET}/${PREFIX_AND_VERSION}/${dir}/${zipfile}"
    VIRTUAL_PARTICIPANT_SRC_S3_LOCATION="${BUCKET}/${PREFIX_AND_VERSION}/${dir}/${zipfile}"
    upload_validate_template "${dir}/template.yaml" "template.yaml" "${PREFIX_AND_VERSION}/${dir}"
}

# Generic function to package a component
package_component() {
    local dir=$1
    local template_dir="${2:-.}"
    local template_file="${3:-template.yaml}"
    local s3_prefix="${4:-${dir}}"
    
    if haschanged ${dir}; then
        echo "PACKAGING ${dir}"
        
        # Check if the component has its own publish script
        if [ -f "${dir}/publish.sh" ]; then
            pushd ${dir} > /dev/null
            chmod +x ./publish.sh
            ./publish.sh $BUCKET $PREFIX_AND_VERSION $REGION || exit 1
            popd > /dev/null
        # Check if the component has a build-s3-dist.sh script
        elif [ -f "${dir}/deployment/build-s3-dist.sh" ]; then
            pushd ${dir}/deployment > /dev/null
            rm -rf ../out
            chmod +x ./build-s3-dist.sh
            ./build-s3-dist.sh $BUCKET_BASENAME $PREFIX_AND_VERSION/${s3_prefix} $VERSION $REGION || exit 1
            popd > /dev/null
        # Default CloudFormation packaging
        elif [ -f "${dir}/${template_dir}/${template_file}" ]; then
            pushd ${dir}/${template_dir} > /dev/null
            package_template "." "${template_file}" "${PREFIX_AND_VERSION}/${s3_prefix}"
            popd > /dev/null
        else
            echo "No template or publish script found in ${dir}"
        fi
        
        update_checksum ${dir}
    else
        echo "SKIPPING ${dir} (unchanged)"
    fi
}

# Process LLM template setup stack with special hash handling
process_llm_template() {
    local dir="lma-llm-template-setup-stack"
    
    if haschanged ${dir}; then
        echo "PACKAGING ${dir}/deployment"
        pushd ${dir}/deployment > /dev/null
        
        # Hash the source folder contents
        echo "Computing hash of src folder contents"
        local hash=$(calculate_hash "../source")
        local template="llm-template-setup.yaml"
        
        echo "Replace hash in template"
        # Handle different sed variants
        if sed --version 2>/dev/null | grep -q GNU; then # GNU sed
            sed -i 's/source_hash: .*/source_hash: '"$hash"'/' ${template}
        else # BSD like sed
            sed -i '' 's/source_hash: .*/source_hash: '"$hash"'/' ${template}
        fi
        
        package_template "." "${template}" "${PREFIX_AND_VERSION}/lma-llm-template-setup-stack"
        popd > /dev/null
        
        update_checksum ${dir}
    else
        echo "SKIPPING ${dir} (unchanged)"
    fi
}

# Process QnABot submodule
process_qnabot() {
    local dir="submodule-aws-qnabot"
    echo "UPDATING ${dir}"
    
    # Update submodule
    git submodule init
    echo "Removing any QnAbot changes from previous builds"
    pushd ${dir} > /dev/null
    git checkout .
    popd > /dev/null
    git submodule update
    
    # Apply customizations
    echo "Applying patch files to remove unused KMS keys from QnABot and customize designer settings page"
    cp -v ./patches/qnabot/templates_examples_examples_index.js ${dir}/source/templates/examples/examples/index.js
    cp -v ./patches/qnabot/templates_examples_extensions_index.js ${dir}/source/templates/examples/extensions/index.js
    cp -v ./patches/qnabot/website_js_lib_store_api_actions_settings.js ${dir}/source/website/js/lib/store/api/actions/settings.js
    
    echo "modify QnABot version string from 'N.N.N' to 'N.N.N-lma'"
    # Handle different sed variants
    if sed --version 2>/dev/null | grep -q GNU; then # GNU sed
        sed -i 's/"version": *"\([0-9]*\.[0-9]*\.[0-9]*\)"/"version": "\1-lma"/' ${dir}/source/package.json
    else # BSD like sed
        sed -i '' 's/"version": *"\([0-9]*\.[0-9]*\.[0-9]*\)"/"version": "\1-lma"/' ${dir}/source/package.json
    fi
    
    echo "Creating config.json"
    cat > ${dir}/source/config.json <<_EOF
{
  "profile": "${AWS_PROFILE:-default}",
  "region": "${REGION}",
  "buildType": "Custom",
  "skipCheckTemplate":true,
  "noStackOutput": true
}
_EOF
    
    # Only rebuild if patches or submodule changed
    if haschanged ./patches/qnabot || hassubmodulechanged ${dir}; then
        echo "PACKAGING ${dir}"
        
        pushd ${dir}/source > /dev/null
        mkdir -p build/templates/dev
        npm install
        npm run build || exit 1
        
        # Rename OpensearchDomain resource in template
        cat ./build/templates/master.json | \
            sed -e "s%OpensearchDomain%LMAQnaBotOpensearchDomain%g" > \
            ./build/templates/qnabot-main.json
            
        aws s3 sync ./build/ s3://${BUCKET}/${PREFIX_AND_VERSION}/aws-qnabot/ --delete
        popd > /dev/null
        
        update_checksum ./patches/qnabot
        update_submodule_hash ${dir}
    else
        echo "SKIPPING ${dir} (unchanged)"
    fi
}

# Process main CloudFormation template
process_main_template() {
    echo "PACKAGING Main Stack Cfn artifacts"
    local main_template="lma-main.yaml"
    
    echo "Inline edit ${main_template} to replace tokens"
    cat ./${main_template} | 
    sed -e "s%<ARTIFACT_BUCKET_TOKEN>%$BUCKET%g" | 
    sed -e "s%<ARTIFACT_PREFIX_TOKEN>%$PREFIX_AND_VERSION%g" |
    sed -e "s%<VERSION_TOKEN>%$VERSION%g" |
    sed -e "s%<REGION_TOKEN>%$REGION%g" |
    sed -e "s%<BROWSER_EXTENSION_SRC_S3_LOCATION_TOKEN>%$BROWSER_EXTENSION_SRC_S3_LOCATION%g" |
    sed -e "s%<VIRTUAL_PARTICIPANT_SRC_S3_LOCATION_TOKEN>%$VIRTUAL_PARTICIPANT_SRC_S3_LOCATION%g" > ${tmpdir}/${main_template}
    
    # Upload main template
    aws s3 cp ${tmpdir}/${main_template} s3://${BUCKET}/${PREFIX}/${main_template} || exit 1
    
    local template="https://s3.${REGION}.amazonaws.com/${BUCKET}/${PREFIX}/${main_template}"
    echo "Validating template: ${template}"
    aws cloudformation validate-template --template-url ${template} > /dev/null || exit 1
    
    # Set public ACLs if requested
    if ${PUBLIC}; then
        echo "Setting public read ACLs on published artifacts"
        files=$(aws s3api list-objects --bucket ${BUCKET} --prefix ${PREFIX_AND_VERSION} --query "(Contents)[].[Key]" --output text)
        c=$(echo $files | wc -w)
        counter=0
        for file in $files; do
            aws s3api put-object-acl --acl public-read --bucket ${BUCKET} --key ${file}
            counter=$((counter + 1))
            echo -ne "Progress: $counter/$c files processed\r"
        done
        aws s3api put-object-acl --acl public-read --bucket ${BUCKET} --key ${PREFIX}/${main_template}
        echo ""
        echo "Done."
    fi
    
    echo "OUTPUTS"
    echo "Template URL: ${template}"
    echo "CF Launch URL: https://${REGION}.console.aws.amazon.com/cloudformation/home?region=${REGION}#/stacks/create/review?templateURL=${template}\&stackName=LMA"
    echo "CLI Deploy: aws cloudformation deploy --region ${REGION} --template-file ${tmpdir}/${main_template} --capabilities CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND --stack-name LMA --parameter-overrides S3BucketName=\"\" AdminEmail='admin@example.com' BedrockKnowledgeBaseId='xxxxxxxxxx'"
}

# Main execution flow
main() {
    check_prerequisites
    parse_arguments "$@"
    setup_bucket
    
    # Process browser extension (special case)
    process_browser_extension
    
    # Process virtual participant (special case)
    process_virtual_participant
    
    # Process standard components
    package_component "lma-vpc-stack"
    package_component "lma-cognito-stack" "deployment" "lma-cognito-stack.yaml" "lma-cognito-stack"
    package_component "lma-meetingassist-setup-stack"
    package_component "lma-bedrockkb-stack"
    package_component "lma-bedrockagent-stack"
    package_component "lma-websocket-transcriber-stack"
    package_component "lma-ai-stack"
    
    # Process LLM template (special case)
    process_llm_template
    
    # Process QnABot (special case)
    process_qnabot
    
    # Process main template
    process_main_template
    
    echo "Done"
}

# Execute main with all arguments
main "$@"
exit 0

