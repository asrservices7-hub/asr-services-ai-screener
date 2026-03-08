# Use Node.js 18 as the base image (full version for build tools)
FROM node:18

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libsqlite3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy root requirements and install Python dependencies
# Use --break-system-packages for Debian bookworm compatibility
COPY all_requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r all_requirements.txt || \
    pip3 install --no-cache-dir -r all_requirements.txt

# Copy backend package.json and install Node dependencies
COPY backend/package*.json ./backend/
RUN cd backend && npm install --production

# Copy all project files
COPY . .

# Set environment variables
ENV PORT=3001
ENV PYTHONUNBUFFERED=1

# Expose the API port
EXPOSE 3001

# Start the backend server
CMD ["node", "backend/server.js"]
