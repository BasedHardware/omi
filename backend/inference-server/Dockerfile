# Use the official CUDA base image
FROM nvidia/cuda:12.3.2-runtime-ubuntu22.04

# Set the working directory
WORKDIR /app

# Install git-lfs repository
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | bash

# Install any necessary dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git-core \
    git-lfs \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Add the requirements file to the container
COPY requirements.txt /app

# Install the required Python packages
RUN pip3 install -r requirements.txt && pip3 install git+https://github.com/m-bain/whisperx.git

# Set the environment variable for production
ENV PRODUCTION=1

# Add the rest of your code to the container
COPY . /app

# Set the entry point for running your inference code
CMD ["python3", "-u", "app.py"]