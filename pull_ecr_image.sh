# Retrieve an authentication token and authenticate your Docker client to your registry:
aws ecr get-login-password --region ap-south-1 | sudo docker login --username AWS --password-stdin 672726205554.dkr.ecr.ap-south-1.amazonaws.com

# pul this image
sudo docker pull 672726205554.dkr.ecr.ap-south-1.amazonaws.com/jee-rankup-ocr-ecr-repo:latest