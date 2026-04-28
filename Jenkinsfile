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
        SERVICE_PORT = '8001'

        // VPS
        VPS_HOST = '172.105.124.43'

        // Temporary credential files — disimpan di /tmp, bukan workspace root
        TMP_ENV_FILE = "/tmp/arna_site_${BUILD_NUMBER}.env"
        TMP_PEM_FILE = "/tmp/arna_site_${BUILD_NUMBER}.pem"
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

        stage('Inject Env & Keys') {
            steps {
                withCredentials([
                    file(credentialsId: 'arna-site-env',  variable: 'ENV_FILE'),
                    file(credentialsId: 'sso_public_pem', variable: 'PUB_KEY_FILE')
                ]) {
                    sh 'cp "$ENV_FILE"     "$TMP_ENV_FILE"'
                    sh 'cp "$PUB_KEY_FILE" "$TMP_PEM_FILE"'
                }
            }
        }

        stage('Build & Push Docker Image') {
            steps {
                script {
                    // Salin ke workspace hanya saat dibutuhkan build context
                    sh 'cp "$TMP_ENV_FILE" .env && cp "$TMP_PEM_FILE" public.pem'

                    withCredentials([
                        usernamePassword(
                            credentialsId: DOCKER_REGISTRY_CREDENTIALS,
                            usernameVariable: 'DOCKER_USER',
                            passwordVariable: 'DOCKER_PASS'
                        )
                    ]) {
                        def cloudBuilt = false
                        try {
                            echo '[INFO] Attempting Docker Build Cloud...'
                            sh """
                                echo "\$DOCKER_PASS" | docker login -u "\$DOCKER_USER" --password-stdin
                                docker buildx create --use --driver cloud \$DOCKER_USER/default
                                docker buildx build --push \\
                                    -t ${DOCKER_IMAGE}:${DOCKER_TAG} \\
                                    -t ${DOCKER_IMAGE}:latest \\
                                    .
                            """
                            cloudBuilt = true
                            echo '[INFO] Docker Build Cloud succeeded.'
                        } catch (e) {
                            echo "[WARN] Docker Build Cloud tidak tersedia, fallback ke local build. Reason: ${e.message}"
                        }

                        if (!cloudBuilt) {
                            docker.withRegistry('https://index.docker.io/v1/', DOCKER_REGISTRY_CREDENTIALS) {
                                def img = docker.build("${DOCKER_IMAGE}:${DOCKER_TAG}", '.')
                                img.push()
                                img.push('latest')
                            }
                        }
                    }

                    // Hapus credential dari workspace root setelah build selesai
                    sh 'rm -f .env public.pem'
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
                    ),
                    usernamePassword(
                        credentialsId: DOCKER_REGISTRY_CREDENTIALS,
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PASS'
                    )
                ]) {
                    sh """
                        echo "[INFO] Preparing VPS deployment..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} \
                            "mkdir -p /root/${STACK_NAME}"

                        echo "[INFO] Copying .env to VPS..."
                        scp -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no \
                            "\$TMP_ENV_FILE" root@${VPS_HOST}:/root/${STACK_NAME}/.env

                        echo "[INFO] Logging in to Docker Hub on VPS..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} \
                            "echo '\$DOCKER_PASS' | docker login -u '\$DOCKER_USER' --password-stdin"

                        echo "[INFO] Deploying to Docker Swarm..."
                        ssh -i "\$SSH_KEY_FILE" -o StrictHostKeyChecking=no root@${VPS_HOST} <<'EOF'
set -e

docker swarm init 2>/dev/null || true
docker network create --driver overlay ${NETWORK_NAME} 2>/dev/null || true

docker pull ${DOCKER_IMAGE}:${DOCKER_TAG}

if docker service ls --format '{{.Name}}' | grep -wq "${STACK_NAME}"; then
    echo "[INFO] Service exists — performing rolling update..."
    docker service update \\
        --image ${DOCKER_IMAGE}:${DOCKER_TAG} \\
        --with-registry-auth \\
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
        --with-registry-auth \\
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
            sh 'rm -f "$TMP_ENV_FILE" "$TMP_PEM_FILE"'
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
