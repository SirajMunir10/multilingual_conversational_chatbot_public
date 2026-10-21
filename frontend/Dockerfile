# Build Stage: Next.js static export (out/)
FROM node:20-alpine AS build-stage

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
# Backend locations are baked in at build time. Empty API base = same origin (nginx proxies /api below).
ARG NEXT_PUBLIC_API_BASE=
ARG NEXT_PUBLIC_API_WS_BASE=
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE NEXT_PUBLIC_API_WS_BASE=$NEXT_PUBLIC_API_WS_BASE NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Production Stage
FROM nginx:alpine AS production-stage

COPY --from=build-stage /app/out /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
