# Use the official Python image as the base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file to the working directory
COPY requirements.txt .

# Install the required Python packages
RUN pip install -r requirements.txt

# Copy the Flask application code to the container
COPY  main.py .

# Start the Flask application when the container starts
CMD ["python", "main.py"]