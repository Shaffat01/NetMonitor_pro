pipeline {
    agent any

    environment {
        DOCKER_USER = 'shaffat01'
        IMAGE_NAME = 'netmonitor-app'
        IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout Code') {
            steps {
                echo '📥 Pulling code from GitHub...'
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "🐳 Building Image: ${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG}"
                sh "docker build -t ${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG} ."
                sh "docker tag ${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG} ${DOCKER_USER}/${IMAGE_NAME}:latest"
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo '🔐 Logging in to Docker Hub & Pushing Image...'
                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-credentials', 
                    passwordVariable: 'DOCKER_PASS', 
                    usernameVariable: 'DOCKER_USER_ENV'
                )]) {
                    sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER_ENV --password-stdin'
                    sh "docker push ${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG}"
                    sh "docker push ${DOCKER_USER}/${IMAGE_NAME}:latest"
                }
            }
        }

        stage('Deploy Application') {
            steps {
                echo '🚀 Deploying container from Docker Hub on Port 8085...'
                sh """
                    docker stop netmonitor-app-hub-container || true
                    docker rm netmonitor-app-hub-container || true
                    docker run -d --name netmonitor-app-hub-container -p 8086:80 ${DOCKER_USER}/${IMAGE_NAME}:${IMAGE_TAG}
                """
            }
        }
    }

    post {
        always {
            echo '🧹 Cleaning up local dangling images...'
            sh 'docker image prune -f || true'
        }
        success {
            echo "🎉 SUCCESS: Image pushed to Docker Hub and App Live on Port 8085!"
        }
        failure {
            echo "❌ FAILURE: Docker Hub Push or Deployment failed!"
        }
    }
}
