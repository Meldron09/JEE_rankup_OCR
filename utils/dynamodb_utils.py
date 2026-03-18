import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from utils.helpers import Colors

load_dotenv()

dynamodb = boto3.resource(
    service_name="dynamodb",
    region_name=os.getenv("AWS_DEFAULT_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

def update_task_completed(table_name: str, task_id: str, output_s3_key: str):
    """
    Update the DynamoDB task record to COMPLETED and record the output S3 key.
 
    Reads DYNAMODB_TABLE and TASK_ID from environment variables.
 
    Args:
        output_s3_key : S3 key prefix of the uploaded output folder
                        (e.g. "output/report")
    """
 
    if not table_name or not task_id:
        print(f"{Colors.YELLOW}Skipping DynamoDB update: "
              f"DYNAMODB_TABLE or TASK_ID not set.{Colors.RESET}")
        return
 
    try:
        table = dynamodb.Table(table_name)
        table.update_item(
                    Key={"task_id": task_id},
                    UpdateExpression="SET #s = :s, output_s3_key = :o",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":s": "COMPLETED",
                        ":o": output_s3_key,
                    },
                    ConditionExpression="attribute_exists(task_id)"
                )
        print(f"{Colors.GREEN}DynamoDB updated:{Colors.RESET} task_id={task_id} "
              f"status=COMPLETED output_s3_key={output_s3_key}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print(f"{Colors.YELLOW}Task {task_id} does not exist. Skipping update.{Colors.RESET}")
            return
        else:
            print(f"{Colors.RED}DynamoDB update failed: {e}{Colors.RESET}")
            raise