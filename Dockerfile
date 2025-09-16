FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt (optional)
# If your script has dependencies, create a requirements.txt file and uncomment the next two lines
COPY requirements.txt .
RUN pip install -r requirements.txt

# Run the Python script
CMD ["python", "runner.py"]