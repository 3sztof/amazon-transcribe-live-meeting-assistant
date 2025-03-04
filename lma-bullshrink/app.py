#!/usr/bin/env python3
from aws_cdk import App, Environment, CfnParameter
from cdk_stacks.app_stack import BullShrinkAppStack

app = App()


BullShrinkAppStack(
    scope=app,
    construct_id="BullShrinkAppStack",
    env=Environment(
        account=app.account,
        region=app.region,
    ),
    description="BullShrink application stack",
)

app.synth()
