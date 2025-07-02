ARG BASE_IMAGE=python:3.13.3-bullseye
ARG ENVIRONMENT
ARG ZSH_CUSTOM

FROM ${BASE_IMAGE} AS build

LABEL maintainer="Jean Dormehl <jean.dormehl@qlink.co.za>"

COPY . /app
COPY ./.devcontainer/conf/start.sh /start.sh

WORKDIR /app

RUN  apt-get update && apt-get install -y --no-install-recommends zsh curl \
  && pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir poetry \
  && poetry update \
  && git config --global --add safe.directory /app \
  && prisma py fetch \
  && chmod +x ./manage.sh && chmod +x /start.sh  \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*


FROM build AS build-dev

# nano, ZSH and various other plugins for local development
RUN apt-get update && apt-get install -y --no-install-recommends git nano \
  && sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" \
  && git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions \
  && git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting \
  && git clone https://github.com/zdharma-continuum/fast-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/fast-syntax-highlighting \
  && chsh -s /bin/zsh root \
  && poetry install --no-root --extras "dev" \
  && sed -i "s/plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting)/g" ~/.zshrc \
  && sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="random"/g' ~/.zshrc \
  && echo "alias cls='clear; pwd'" >> ~/.zshrc \
  && echo 'm() { /app/manage.sh "$@" }' >> ~/.zshrc \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
