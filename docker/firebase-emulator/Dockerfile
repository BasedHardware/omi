FROM node:20-slim

RUN apt-get update && \
    apt-get install -y openjdk-17-jre-headless curl && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g firebase-tools@13

WORKDIR /firebase

COPY firebase.json .
COPY storage.rules .

EXPOSE 4000 8080 9099 9199

CMD ["firebase", "emulators:start", "--project", "demo-omi-local", "--only", "firestore,auth,storage"]
