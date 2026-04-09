pipeline {
    agent any

    environment {
        DEPLOY = 'true'

        // Docker
        DOCKER_IMAGE = 'ardzix/arna_site'
        DOCKER_TAG = "${BUILD_NUMBER}"
        DOCKER_REGISTRY_CREDENTIALS = 'ard-dockerhub'

        // Swarm
        STACK_NAME = 'arna_site'
        REPLICAS = '1'
        NETWORK_NAME = 'production'
        SERVICE_PORT = '8002' // Port eksternal yang terekspos

        // VPS
        VPS_HOST = '172.105.124.43'
    }

    stages {

        stage('Clean Workspace') {
            steps {
                deleteDir()
            }
        }

        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        // Suntikkan file environment dan public_key (untuk auth lokal JWT Admin API)
        stage('Inject Env & Keys') {
            steps {
                withCredentials([
                    file(credentialsId: 'arna-site-env', variable: 'ENV_FILE'),
                    file(credentialsId: 'arna-sso-public-key', variable: 'PUB_KEY_FILE')
                ]) {
                    sh 'cp "$ENV_FILE" .env'
                    sh 'mkdir -p ssl'
                    sh 'cp "$PUB_KEY_FILE" ssl/public.pem'
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    docker.build("${DOCKER_IMAGE}:${DOCKER_TAG}", ".")
                }
            }
        }

        stage('Push Docker Image') {
            steps {
                script {
                    docker.withRegistry('https://index.docker.io/v1/', DOCKER_REGISTRY_CREDENTIALS) {
                        docker.image("${DOCKER_IMAGE}:${DOCKER_TAG}").push()
                        docker.image("${DOCKER_IMAGE}:${DOCKER_TAG}").push('latest')
                    }
                }
            }
        }

        stage('Deploy to Swarm') {
            when {
                expression { return env.DEPLOY?.toBoolean() ?: false }
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'stag-arnatech-sa-01',
                        keyFileVariable: 'SSH_KEY_FILE'
                    )
                ]) {
                    sh """
                        echo "[INFO] Preparing VPS deployment..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} "mkdir -p /root/${STACK_NAME}"

                        echo "[INFO] Copying env..."
                        scp -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no .env root@${VPS_HOST}:/root/${STACK_NAME}/.env

                        echo "[INFO] Deploying Docker service..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} <<EOF
set -e

docker swarm init || true
docker network create --driver overlay ${NETWORK_NAME} || true

if docker service ls | awk '{print \\\$2}' | grep -wq ${STACK_NAME}; then
    echo "[INFO] Service found. Performing rolling update..."
    docker service update \\
        --image ${DOCKER_IMAGE}:${DOCKER_TAG} \\
        --env-add file=/root/${STACK_NAME}/.env \\
        --update-delay 10s \\
        ${STACK_NAME}
else
    echo "[INFO] Service not found. Creating new service..."
    docker service create \\
        --name ${STACK_NAME} \\
        --replicas ${REPLICAS} \\
        --network ${NETWORK_NAME} \\
        --env-file /root/${STACK_NAME}/.env \\
        --publish ${SERVICE_PORT}:8002 \\
        ${DOCKER_IMAGE}:${DOCKER_TAG}
fi

echo "[INFO] Running Django Multi-Tenant Migrations..."
docker run --rm \\
    --network ${NETWORK_NAME} \\
    --env-file /root/${STACK_NAME}/.env \\
    ${DOCKER_IMAGE}:${DOCKER_TAG} \\
    sh -c "python manage.py migrate_schemas --shared && python manage.py migrate_schemas && python manage.py setup_domain"

echo "[INFO] Deploy success."
EOF
                    """
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline finished!'
        }
        success {
            echo 'Deployment successful!'
        }
        failure {
            echo 'Pipeline failed.'
        }
    }
}