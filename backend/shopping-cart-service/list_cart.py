import json
import os

import boto3
from aws_lambda_powertools import Logger, Tracer
from boto3.dynamodb.conditions import Key

from shared import get_cart_id, get_headers, get_user_sub, handle_decimal_type

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def lambda_handler(event, context):
    """
    List items in shopping cart.
    """

    cart_id, generated = get_cart_id(event["headers"])

    # Because this method can be called anonymously, we need to check there's a logged in user
    jwt_token = event["headers"].get("Authorization")
    if jwt_token:
        user_sub = get_user_sub(jwt_token)
        key_string = f"user#{user_sub}"
        logger.structure_logs(append=True, cart_id=f"user#{user_sub}")
        logger.info(f"Authenticated user in session: {key_string}")
    else:
        key_string = f"cart#{cart_id}"
        logger.structure_logs(append=True, cart_id=f"cart#{cart_id}")
        logger.info(f"Anonymous user in session: {key_string}")

    # No need to query database if the cart_id was generated rather than passed into the function
    if generated:
        logger.info(
            "cart ID was generated in this request, not fetching cart from DB")
        product_list = []
    else:
        logger.info(f"List all items in cart for user : {key_string}")
        response = table.query(
            KeyConditionExpression=Key("pk").eq(key_string)
            & Key("sk").begins_with("product#"),
            ProjectionExpression="sk,quantity,productDetail",
            # Only return items with more than 0 quantity
            FilterExpression="quantity > :val",
            ExpressionAttributeValues={":val": 0},
        )
        product_list = response.get("Items", [])
    logger.info(
        f"Total {len(product_list)} items in the cart for user - {key_string}")

    for product in product_list:
        logger.info(f"Product in user#{key_string} cart - {product}")
        product.update(
            (k, v.replace("product#", "")) for k, v in product.items() if k == "sk"
        )

    return {
        "statusCode": 200,
        "headers": get_headers(cart_id),
        "body": json.dumps({"products": product_list}, default=handle_decimal_type),
    }
