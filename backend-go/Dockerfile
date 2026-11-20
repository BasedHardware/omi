FROM --platform=$BUILDPLATFORM golang:1.27.0-bookworm@sha256:ded31c68586d2e49e760acc2e65a884b23d032e9bbbed0ae0c55abd3fcaf4452 AS build
WORKDIR /src
ENV GOTOOLCHAIN=local
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/workerd ./cmd/workerd
COPY internal ./internal
ARG TARGETOS TARGETARCH
RUN CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
    go build -mod=readonly -trimpath -o /workerd ./cmd/workerd

FROM gcr.io/distroless/static-debian13:nonroot@sha256:aafe993665bf6200db38a02c11a9351e782a84b6a45e7f33b6695638c88e3931
COPY --from=build /workerd /workerd
USER 65532:65532
EXPOSE 8080 9090
ENTRYPOINT ["/workerd"]
