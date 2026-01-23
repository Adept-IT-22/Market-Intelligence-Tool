# Stage 1: Build the Angular application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the source code
COPY . .

# Build the application for production
# Verify the output path in angular.json, but standard v17+ is dist/<project-name>/browser
RUN npm run build -- --configuration production

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy the build output from the previous stage
# Note: Ensure 'market-intelligence' matches the project name in angular.json
COPY --from=build /app/dist/market-intelligence/browser /usr/share/nginx/html

# Copy a custom Nginx configuration if needed (optional but recommended for SPA routing)
# We will create a simple nginx.conf inline or assume default for now, 
# but for SPA we strictly need try_files $uri $uri/ /index.html;
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
