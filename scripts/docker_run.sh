#!/bin/bash

source .env

docker build -t "${DEFAULT_DOCKER_TAG}" . && \
    docker run -t "${DEFAULT_DOCKER_TAG}" $@
