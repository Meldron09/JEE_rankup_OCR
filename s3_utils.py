import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize S3 client
s3 = boto3.client(service_name='s3', region_name=os.getenv('AWS_DEFAULT_REGION'), 
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'), 
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'))

def upload_folder(bucket, object_key, local_folder):
    base_folder = os.path.basename(os.path.normpath(local_folder))

    for root, dirs, files in os.walk(local_folder):
        for file in files:
            local_path = os.path.join(root, file)

            # relative path inside the folder
            relative_path = os.path.relpath(local_path, local_folder)

            # include base folder in S3
            s3_key = os.path.join(s3_prefix, base_folder, relative_path)

            # normalize for S3
            s3_key = s3_key.replace("\\", "/")

            try:
                s3.upload_file(local_path, bucket, s3_key)
                print(f"Uploaded: {local_path} -> s3://{bucket}/{s3_key}")
            except Exception as e:
                print(f"Failed: {local_path} ({e})")


def download_file(bucket, object_key, file_name):
    """Download a file from an S3 bucket"""
    try:
        s3.download_file(Bucket=bucket, Key=object_key, Filename=file_name)
        print(f"Download successful: s3://{bucket}/{object_key} -> {file_name}")
    except FileNotFoundError:
        print("The destination path is invalid")
    except NoCredentialsError:
        print("Credentials not available")
    except ClientError as e:
        print(f"Download failed: {e}")

