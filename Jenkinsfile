pipeline {
    agent any

    environment {
        IMAGE_NAME = "netmonitor-pro"
        CONTAINER_NAME = "netmonitor_app"
    }

    stages {
        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    echo 'Building Optimized Docker Image...'
                    sh 'docker-compose build'
                }
            }
        }

        stage('Deploy to Server') {
            steps {
                script {
                    echo 'Deploying application...'
                    sh 'docker-compose down'
                    sh 'docker-compose up -d -p 8086:80'
                }
            }
        }
        
        stage('Clean Up') {
            steps {
                script {
                    echo 'Cleaning up old unused Docker images to save space...'
                    sh 'docker image prune -f'
                }
            }
        }
    }

    post {
        success {
            echo "✅ Deployment Successful! App is running on Port 3000."
        }
        failure {
            echo "❌ Deployment Failed! Please check the Jenkins logs."
        }
    }
}
