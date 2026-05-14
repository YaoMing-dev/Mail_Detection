@echo off
setlocal

set "REPO_DIR=%~dp0.."
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.0.19.10-hotspot"
set "MAVEN_HOME=D:\tools\apache-maven-3.9.15"
set "PATH=%JAVA_HOME%\bin;%MAVEN_HOME%\bin;%PATH%"

subst M: /D >nul 2>nul
subst M: "%REPO_DIR%"

set "MONGODB_URI=mongodb://localhost:27017/mail_ocr"
set "MAIL_OCR_PROJECT_ROOT=M:\"
set "MAIL_OCR_PYTHON=M:\.venv312\Scripts\python.exe"
set "MAIL_OCR_BACKEND=vietocr"

cd /d M:\backend-spring
mvn.cmd spring-boot:run
