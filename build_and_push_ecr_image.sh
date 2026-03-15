# Retrieve an authentication token and authenticate your Docker client to your registry:
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 672726205554.dkr.ecr.ap-south-1.amazonaws.com

# Build your Docker image
docker build -t jee-rankup-ocr-ecr-repo .

# tag your image so you can push the image to this repository
docker tag jee-rankup-ocr-ecr-repo:latest 672726205554.dkr.ecr.ap-south-1.amazonaws.com/jee-rankup-ocr-ecr-repo:latest

# push this image to your newly created AWS repository
docker push 672726205554.dkr.ecr.ap-south-1.amazonaws.com/jee-rankup-ocr-ecr-repo:latest