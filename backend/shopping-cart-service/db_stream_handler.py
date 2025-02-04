import os
from collections import Counter

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb import types

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

deserializer = types.TypeDeserializer()


@tracer.capture_method
def dynamodb_to_python(dynamodb_item):
    """
    Convert from dynamodb low level format to python dict
    """
    return {k: deserializer.deserialize(v) for k, v in dynamodb_item.items()}


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    """
    Handle streams from DynamoDB table
    """

    records = event["Records"]
    quantity_change_counter = Counter()

    for record in records:
        keys = dynamodb_to_python(record["dynamodb"]["Keys"])
        event_name = record.get("eventName", "")
        logger.info(f"Current dynamo event - {event_name}")
        # NewImage record only exists if the event is INSERT or MODIFY
        if record["eventName"] in ("INSERT", "MODIFY"):
            new_image = dynamodb_to_python(record["dynamodb"]["NewImage"])
            logger.info(
                f"New image for dynamo db since this is a modification event - {event_name}")
        else:
            new_image = {}

        old_image_ddb = record["dynamodb"].get("OldImage")

        if old_image_ddb:
            old_image = dynamodb_to_python(
                record["dynamodb"].get("OldImage")
            )  # Won't exist in case event is INSERT
        else:
            old_image = {}

        # We want to record the quantity change the change made to the db rather than absolute values
        if keys["sk"].startswith("product#"):
            qty_change = new_image.get(
                "quantity", 0) - old_image.get("quantity", 0)
            logger.info(
                f"Recording the change in quantity made to dynamo db - {qty_change}")
            quantity_change_counter.update(
                {
                    keys["sk"]: qty_change
                }
            )

    for k, v in quantity_change_counter.items():
        logger.info(f"Recording change in quantity count - {k} : {v}")
        table.update_item(
            Key={"pk": k, "sk": "totalquantity"},
            ExpressionAttributeNames={"#quantity": "quantity"},
            ExpressionAttributeValues={":val": v},
            UpdateExpression="ADD #quantity :val",
        )

    return {
        "statusCode": 200,
    }
