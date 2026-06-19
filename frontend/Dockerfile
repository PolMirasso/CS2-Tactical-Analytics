FROM node:22-alpine AS builder

WORKDIR /app

# Install deps first for better layer caching (copies package-lock.json if present).
COPY package*.json ./
RUN npm install

COPY . .

# Vite bakes VITE_* vars at build time. Override with
#   docker build --build-arg VITE_API_BASE_URL=https://api.example.com
# or via the compose `args` block.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO /dev/null http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
