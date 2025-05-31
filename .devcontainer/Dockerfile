FROM python:3.13.3-bullseye

ARG ENVIRONMENT
ARG TZ
ARG ZSH_CUSTOM

LABEL maintainer="Jean Dormehl <jean.dormehl@qlink.co.za>"

ENV ENVIRONMENT=${ENVIRONMENT}
ENV TZ=${TZ}

COPY . /app
COPY ./.devcontainer/conf/start.sh /start.sh

# nano, ZSH and various other plugins for local development
RUN apt-get update && apt-get install -y --no-install-recommends zsh git curl nano \
  && sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" \
  && git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions \
  && git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting \
  && git clone https://github.com/zdharma-continuum/fast-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/fast-syntax-highlighting \
  && chsh -s /bin/zsh root \
  && sed -i "s/plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting)/g" ~/.zshrc \
  && sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="random"/g' ~/.zshrc \
  && echo "alias cls='clear; pwd'" >> ~/.zshrc \
  && echo 'm() { /app/manage.sh "$@" }' >> ~/.zshrc

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir poetry \
  && /usr/local/bin/poetry config virtualenvs.create false \
  && /usr/local/bin/poetry update \
  && chmod +x ./manage.sh && chmod +x /start.sh
