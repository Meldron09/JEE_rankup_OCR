import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import os
from dotenv import load_dotenv
from utils.helpers import Colors

load_dotenv()

# Initialize S3 client
s3 = boto3.client(service_name='s3', region_name=os.getenv('AWS_DEFAULT_REGION'), 
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'), 
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))


def upload_folder(bucket: str, s3_prefix: str, local_folder: str):
    """
    Upload an entire local folder to S3.

    The S3 key for each file will be:
        <s3_prefix>/<base_folder_name>/<relative_path_inside_folder>

    Args:
        bucket       : S3 bucket name
        s3_prefix    : Key prefix inside the bucket (e.g. "output")
        local_folder : Local directory to upload
    """
    base_folder = os.path.basename(os.path.normpath(local_folder))

    for root, dirs, files in os.walk(local_folder):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_folder)
            s3_key = os.path.join(s3_prefix, base_folder, relative_path).replace("\\", "/")

            try:
                s3.upload_file(local_path, bucket, s3_key)
                print(f"{Colors.GREEN}Uploaded:{Colors.RESET} {local_path} -> s3://{bucket}/{s3_key}")
            except Exception as e:
                print(f"{Colors.RED}Failed to upload {local_path}: {e}{Colors.RESET}")

def download_file(bucket: str, object_key: str, local_path: str):
    """
    Download a single file from S3 to a local path.

    Args:
        bucket     : S3 bucket name
        object_key : Full S3 key of the object (e.g. "input/report.pdf")
        local_path : Destination path on local disk
    """
    try:
        s3.download_file(Bucket=bucket, Key=object_key, Filename=local_path)
        print(f"{Colors.GREEN}Downloaded:{Colors.RESET} s3://{bucket}/{object_key} -> {local_path}")
    except FileNotFoundError:
        print(f"{Colors.RED}Destination path is invalid: {local_path}{Colors.RESET}")
        raise
    except NoCredentialsError:
        print(f"{Colors.RED}AWS credentials not available.{Colors.RESET}")
        raise
    except ClientError as e:
        print(f"{Colors.RED}S3 download failed: {e}{Colors.RESET}")
        raise
