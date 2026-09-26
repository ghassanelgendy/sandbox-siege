FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY server.mjs ./

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -q -O - http://localhost:8090/health || exit 1

CMD ["node", "server.mjs"]
