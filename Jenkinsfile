pipeline {
    agent any

    environment {
        DEPLOY = 'true'

        // Docker
        DOCKER_IMAGE = 'arnatechid/arna_site'
        DOCKER_TAG   = "${BUILD_NUMBER}"
        DOCKER_REGISTRY_CREDENTIALS = 'ard-dockerhub'

        // Swarm
        STACK_NAME   = 'arna_site'
        REPLICAS     = '1'
        NETWORK_NAME = 'production'
        SERVICE_PORT = '8001'   // Port eksternal (host:container)

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

        // Inject .env dan public.pem ke root project sebelum docker build
        stage('Inject Env & Keys') {
            steps {
                withCredentials([
                    file(credentialsId: 'arna-site-env',   variable: 'ENV_FILE'),
                    file(credentialsId: 'sso_public_pem',  variable: 'PUB_KEY_FILE')
                ]) {
                    sh 'cp "$ENV_FILE"     .env'
                    sh 'cp "$PUB_KEY_FILE" public.pem'
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
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} \
                            "mkdir -p /root/${STACK_NAME}"

                        echo "[INFO] Copying .env to VPS..."
                        scp -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no \
                            .env root@${VPS_HOST}:/root/${STACK_NAME}/.env

                        echo "[INFO] Deploying to Docker Swarm..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} <<'EOF'
set -e

# Init swarm and network if not already done
docker swarm init 2>/dev/null || true
docker network create --driver overlay ${NETWORK_NAME} 2>/dev/null || true

if docker service ls --format '{{.Name}}' | grep -wq "${STACK_NAME}"; then
    echo "[INFO] Service exists — performing rolling update..."
    docker service update \\
        --image ${DOCKER_IMAGE}:${DOCKER_TAG} \\
        --update-delay 10s \\
        --update-order start-first \\
        --update-failure-action rollback \\
        ${STACK_NAME}
else
    echo "[INFO] Creating new service..."
    docker service create \\
        --name ${STACK_NAME} \\
        --replicas ${REPLICAS} \\
        --network ${NETWORK_NAME} \\
        --env-file /root/${STACK_NAME}/.env \\
        --publish ${SERVICE_PORT}:8001 \\
        --update-delay 10s \\
        --update-order start-first \\
        --update-failure-action rollback \\
        --restart-condition on-failure \\
        --restart-max-attempts 3 \\
        ${DOCKER_IMAGE}:${DOCKER_TAG}
fi

echo "[INFO] Deploy success."
EOF
                    """
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline finished.'
        }
        success {
            echo "Deployed ${DOCKER_IMAGE}:${DOCKER_TAG} successfully."
        }
        failure {
            echo 'Pipeline failed. Check logs above.'
        }
    }
}
