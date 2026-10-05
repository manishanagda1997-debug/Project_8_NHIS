# Web server image: Nginx in front of the application server (decision D-038).
# Build from the project root:  docker compose build
FROM nginx:1.27.3-alpine
COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
