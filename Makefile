# Define the image name and tag
IMAGE_NAME := conductor-evaluation-distributor
TAG := latest

# Define the build target
.PHONY: build
build: ## Build the Docker image
	docker build -t $(IMAGE_NAME):$(TAG) .

# Define the run target
.PHONY: run
run: build ## Build and run the Docker container
	docker run --rm $(IMAGE_NAME):$(TAG)
