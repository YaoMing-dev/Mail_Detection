package com.mailocr.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail-ocr")
public class MailOcrProperties {
  private String projectRoot;
  private String pythonExecutable;
  private String modelPath;
  private String outputDir;
  private String uploadDir;
  private String defaultOcrBackend;
  private String allowedOrigin;

  public String getProjectRoot() {
    return projectRoot;
  }

  public void setProjectRoot(String projectRoot) {
    this.projectRoot = projectRoot;
  }

  public String getPythonExecutable() {
    return pythonExecutable;
  }

  public void setPythonExecutable(String pythonExecutable) {
    this.pythonExecutable = pythonExecutable;
  }

  public String getModelPath() {
    return modelPath;
  }

  public void setModelPath(String modelPath) {
    this.modelPath = modelPath;
  }

  public String getOutputDir() {
    return outputDir;
  }

  public void setOutputDir(String outputDir) {
    this.outputDir = outputDir;
  }

  public String getUploadDir() {
    return uploadDir;
  }

  public void setUploadDir(String uploadDir) {
    this.uploadDir = uploadDir;
  }

  public String getDefaultOcrBackend() {
    return defaultOcrBackend;
  }

  public void setDefaultOcrBackend(String defaultOcrBackend) {
    this.defaultOcrBackend = defaultOcrBackend;
  }

  public String getAllowedOrigin() {
    return allowedOrigin;
  }

  public void setAllowedOrigin(String allowedOrigin) {
    this.allowedOrigin = allowedOrigin;
  }
}
