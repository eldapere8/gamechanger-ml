#!/usr/bin/env bash
#set -o errexit
#set -o nounset
#set -o pipefail

ENV_TYPE="${1:-${ENV_TYPE:-}}"
DOWNLOAD_DEP="${2:-${DOWNLOAD_DEP:-}}"

[[ -z "${ENV_TYPE}" ]] && {
  >&2 echo "[WARNING] [SETUP_ENV SCRIPT] No ENV_TYPE - 1st arg - specified, setting to 'PROD' ..."
  ENV_TYPE="PROD"
}

function setup_prod() {
    echo "[INFO] Setting up PROD environment ..."
    export TRANSFORMER_HOST="${TRANSFORMER_HOST:-http://localhost}"
    export REDIS_HOST="${REDIS_HOST:-localhost}"
    export REDIS_PORT="${REDIS_PORT:-6379}"
    export GC_ML_HOST="${GC_ML_HOST:-http://localhost}"
    export S3_TRANS_MODEL_PATH="${S3_TRANS_MODEL_PATH:-s3://advana-data-zone/bronze/gamechanger/models/transformers/v5/transformers.tar.gz}"
    export S3_SENT_INDEX_PATH="${S3_SENT_INDEX_PATH:-s3://advana-data-zone/bronze/gamechanger/models/sentence_index/v7/sent_index_20210715.tar.gz}"
    export S3_QEXP_PATH="${S3_QEXP_PATH:-s3://advana-data-zone/bronze/gamechanger/models/qexp_model/v3/qexp_20201217.tar.gz}"
    export S3_QEXP_JBOOK_PATH="${S3_QEXP_JBOOK_PATH:-s3://advana-data-zone/bronze/gamechanger/models/jbook_qexp_model/v2/jbook_qexp_20220131.tar}"
    export S3_TOPICS_PATH="${S3_TOPICS_PATH:-s3://advana-data-zone/bronze/gamechanger/models/topic_model/v1/20210208.tar.gz}"
    export S3_ML_DATA_PATH="${S3_ML_DATA_PATH:-s3://advana-data-zone/bronze/gamechanger/ml-data/v1/data_20211018.tar.gz}"
    export S3_CORPUS_PATH="${S3_CORPUS_PATH:-s3://advana-data-zone/bronze/gamechanger/json}"
    export DOWNLOAD_DEP="${DOWNLOAD_DEP:-true}"

    export ES_HOST="${ES_HOST:-}"
    export ES_PORT="${ES_PORT:-443}"
    export ES_USER="${ES_USER:-}"
    export ES_PASSWORD="${ES_PASSWORD:-}"
    export ES_ENABLE_SSL="${ES_ENABLE_SSL:-true}"
    export ES_ENABLE_AUTH="${ES_ENABLE_AUTH:-true}"
  
    export GC_WEB_HOST="${GC_WEB_HOST:-gamechanger.advana.data.mil}"
    export GC_WEB_PORT="${GC_WEB_PORT:-8990}"
    export GC_WEB_USER="${GC_WEB_USER:-steve}"
    export GC_ENABLE_SSL="${GC_ENABLE_SSL:-true}"
    

    export DEV_ENV="PROD"
}

function setup_dev() {
    echo "[INFO] Setting up DEV Docker environment ..."
    export REDIS_HOST="${REDIS_HOST:-gc-redis}"
    export REDIS_PORT="${REDIS_PORT:-6380}"
    export GC_ML_HOST="${GC_ML_HOST:-http://host.docker.internal}"
    export S3_TRANS_MODEL_PATH="${S3_TRANS_MODEL_PATH:-s3://advana-data-zone/bronze/gamechanger/models/transformers/v5/transformers.tar.gz}"
    export S3_SENT_INDEX_PATH="${S3_SENT_INDEX_PATH:-s3://advana-data-zone/bronze/gamechanger/models/sentence_index/v7/sent_index_20210716.tar.gz}"
    export S3_QEXP_PATH="${S3_QEXP_PATH:-s3://advana-data-zone/bronze/gamechanger/models/qexp_model/v4/qexp_20211001.tar.gz}"
    export S3_QEXP_JBOOK_PATH="${S3_QEXP_JBOOK_PATH:-s3://advana-data-zone/bronze/gamechanger/models/jbook_qexp_model/v2/jbook_qexp_20220131.tar}"
    export S3_TOPICS_PATH="${S3_TOPICS_PATH:-s3://advana-data-zone/bronze/gamechanger/models/topic_model/v1/20210208.tar.gz}"
    export S3_ML_DATA_PATH="${S3_ML_DATA_PATH:-s3://advana-data-zone/bronze/gamechanger/ml-data/v1/data_20211018.tar.gz}"
    export S3_CORPUS_PATH="${S3_CORPUS_PATH:-s3://advana-data-zone/bronze/gamechanger/json}"

    export DEV_ENV="DEV"
    export PULL_MODELS="${PULL_MODELS:-latest}"
    export MLFLOW_HOST="${MLFLOW_HOST:-localhost}"
    export MLFLOW_TRACKING_URI="http://${MLFLOW_HOST}:5050/"
    export DOWNLOAD_DEP="${DOWNLOAD_DEP:-false}"
    export MODEL_LOAD="${MODEL_LOAD:-True}"

    export ES_HOST="${ES_HOST:-vpc-gamechanger-dev-es-ms4wkfqyvlyt3gmiyak2hleqyu.us-east-1.es.amazonaws.com}"
    export ES_PORT="${ES_PORT:-443}"
    export ES_USER="${ES_USER:-}"
    export ES_PASSWORD="${ES_PASSWORD:-}"
    export ES_ENABLE_SSL="${ES_ENABLE_SSL:-true}"
    export ES_ENABLE_AUTH="${ES_ENABLE_AUTH:-false}"
      
    export GC_WEB_HOST="${GC_WEB_HOST:-10.194.9.88}"
    export GC_WEB_PORT="${GC_WEB_PORT:-8990}"
    export GC_WEB_USER="${GC_WEB_USER:-steve}"
    export GC_ENABLE_SSL="${GC_ENABLE_SSL:-false}"
    
}


function setup_devlocal() {
  echo "[INFO] Setting up DEVLOCAL environment ..."
  export REDIS_HOST="${REDIS_HOST:-localhost}"
  export REDIS_PORT="${REDIS_PORT:-6380}"
  export GC_ML_HOST="${GC_ML_HOST:-http://localhost}"
  export S3_TRANS_MODEL_PATH="${S3_TRANS_MODEL_PATH:-s3://advana-data-zone/bronze/gamechanger/models/transformers/v5/transformers.tar.gz}"
  export S3_SENT_INDEX_PATH="${S3_SENT_INDEX_PATH:-s3://advana-data-zone/bronze/gamechanger/models/sentence_index/v4/sent_index_20210422.tar.gz}"
  export S3_ML_DATA_PATH="${S3_ML_DATA_PATH:-s3://advana-data-zone/bronze/gamechanger/ml-data/v1/data_20211202.tar.gz}"

  export ES_HOST="${ES_HOST:-vpc-gamechanger-dev-es-ms4wkfqyvlyt3gmiyak2hleqyu.us-east-1.es.amazonaws.com}"
  export ES_PORT="${ES_PORT:-443}"
  export ES_USER="${ES_USER:-}"
  export ES_PASSWORD="${ES_PASSWORD:-}"
  export ES_ENABLE_SSL="${ES_ENABLE_SSL:-true}"
  export ES_ENABLE_AUTH="${ES_ENABLE_AUTH:-false}"

  export DEV_ENV="DEVLOCAL"
}

function setup_k8s_dev() {
  setup_dev
}

function setup_k8s_test() {
  setup_dev
}

function setup_k8s_prod() {
  setup_prod
}

# if set to blank, unset
[[ -z "${AWS_PROFILE:-}" ]] && unset AWS_PROFILE
[[ -z "${AWS_DEFAULT_PROFILE:-}" ]] && unset AWS_DEFAULT_PROFILE

case "$ENV_TYPE" in
  PROD)
    setup_prod
    ;;
  DEV)
    setup_dev
    ;;
  DEVLOCAL)
    setup_devlocal
    ;;
  K8S_DEV)
    setup_k8s_dev
    ;;
  K8S_TEST)
    setup_k8s_test
    ;;
  K8S_PROD)
    setup_k8s_prod
    ;;
  *)
    >&2 echo "[ERROR] Invalid ENV_TYPE specified: '$ENV_TYPE'"
    ;;
esac
cat <<EOF
  ENVIRONMENT SET: ${DEV_ENV:-<unset>} "
  * AWS SETTING: ${DEV_ENV:-<unset>} "
  * TRANSFORMER HOSTNAME: ${TRANSFORMER_HOST:-<unset>} "
  * REDIS HOST: ${REDIS_HOST:-<unset>} "
  * FLASK HOST: ${GC_ML_HOST:-<unset>} "
  * REDIS PORT: ${REDIS_PORT:-<unset>} "
  * PULL MODELS: ${PULL_MODELS:-<unset>} "
  * GC_ML_API_MODEL_NAME: ${GC_ML_API_MODEL_NAME:-<unset>} "
  * S3_TRANS_MODEL_PATH: ${S3_TRANS_MODEL_PATH:-<unset>}"
  * S3_SENT_INDEX_PATH: ${S3_SENT_INDEX_PATH:-<unset>}"
  * S3_QEXP_PATH: ${S3_QEXP_PATH:-<unset>}"
  * S3_QEXP_JBOOK_PATH: ${S3_QEXP_JBOOK_PATH:-<unset>}"
  * S3_ML_DATA_PATH= ${S3_ML_DATA_PATH:-:-<unset>}"
  * S3_TOPICS_PATH: ${S3_TOPICS_PATH:-<unset>}"
  * DOWNLOAD_DEP: ${DOWNLOAD_DEP:-<unset>}"
  * ES_HOST: ${ES_HOST:-<unset>}"
  * GC_WEB_HOST: ${GC_WEB_HOST:-<unset>}"
  * GC_WEB_USER: ${GC_WEB_USER:-<unset>}"
EOF
