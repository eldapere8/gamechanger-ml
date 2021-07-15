ARG BASE_IMAGE="registry.access.redhat.com/ubi8/python-36:1-148"
FROM $BASE_IMAGE

SHELL ["/bin/bash", "-c"]

# tmp switch to root for sys pkg setup
USER root

# LOCALE Prereqs
RUN yum install -y \
        glibc-langpack-en \
    && yum clean all \
    && rm -rf /var/cache/yum


# SET LOCALE TO UTF-8
ENV LANG="en_US.UTF-8"
ENV LANGUAGE="en_US.UTF-8"
ENV LC_ALL="en_US.UTF-8"

# App & Dep Preqrequisites
RUN yum install -y \
        gcc \
        gcc-c++ \
        python36-devel \
        git \
        zip \
        unzip \
        python3-cffi \
        libffi-devel \
        cairo \
    && yum clean all \
    && rm -rf /var/cache/yum

# AWS CLI
RUN curl -LfSo /tmp/awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" \
    && unzip -q /tmp/awscliv2.zip -d /opt \
    && /opt/aws/install \
    && rm -f /tmp/awscliv2.zip

# per convention in red hat python images
ENV APP_ROOT="${APP_ROOT:-/opt/app-root}"
ENV APP_DIR="${APP_ROOT}/src"
RUN mkdir -p "${APP_DIR}" \
    && chown -R 1001:0 "${APP_ROOT}"
WORKDIR "$APP_DIR"

USER 1001
# thou shall not root

COPY --chown=1001:0 ./requirements.txt "$APP_DIR/requirements.txt"
RUN python3 -m venv "$APP_DIR/venv" \
    && "$APP_DIR/venv/bin/python" -m pip install --upgrade --no-cache-dir pip setuptools wheel \
    && "$APP_DIR/venv/bin/python" -m pip install --no-deps --no-cache-dir -r "$APP_DIR/requirements.txt"

COPY --chown=1001:0 . "${APP_DIR}"

ENV MLAPP_VENV_DIR="${APP_DIR}/venv"
EXPOSE 5000
ENTRYPOINT ["/bin/bash", "./gamechangerml/api/fastapi/startFast.sh"]
CMD ["DEV"]