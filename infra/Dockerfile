FROM nginx:1.22.1 AS base
COPY ./infra/nginx.conf /etc/nginx/templates/default.conf.template
COPY ./infra/nginx-log-format.conf /etc/nginx/conf.d/00-log-format.conf
COPY ./infra/index.html /usr/share/nginx/html/
FROM base AS production
