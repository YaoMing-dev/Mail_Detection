package com.mailocr.api.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mailocr.api.config.MailOcrProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class PipelineService {
  private static final Duration TIMEOUT = Duration.ofMinutes(8);

  private final MailOcrProperties properties;
  private final ObjectMapper objectMapper;

  public PipelineService(MailOcrProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.objectMapper = objectMapper;
  }

  public PipelineResult extract(Path imagePath, String requestedBackend) {
    String backend = isSupportedBackend(requestedBackend) ? requestedBackend : properties.getDefaultOcrBackend();
    Path projectRoot = Path.of(properties.getProjectRoot()).toAbsolutePath().normalize();

    List<String> command = new ArrayList<>();
    command.add(resolve(projectRoot, properties.getPythonExecutable()).toString());
    command.add("-X");
    command.add("utf8");
    command.add("src/local_3field_pipeline.py");
    command.add(imagePath.toAbsolutePath().normalize().toString());
    command.add("--model");
    command.add(properties.getModelPath());
    command.add("--out_dir");
    command.add(properties.getOutputDir());
    command.add("--ocr_backend");
    command.add(backend);

    ProcessBuilder builder = new ProcessBuilder(command);
    builder.directory(projectRoot.toFile());
    builder.redirectErrorStream(true);

    try {
      Process process = builder.start();
      CompletableFuture<String> outputFuture = CompletableFuture.supplyAsync(() -> {
        try {
          return new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
          throw new PipelineException("Cannot read pipeline output.", e);
        }
      });
      boolean finished = process.waitFor(TIMEOUT.toSeconds(), TimeUnit.SECONDS);
      if (!finished) {
        process.destroyForcibly();
        throw new PipelineException("Pipeline timed out after " + TIMEOUT.toMinutes() + " minutes.");
      }
      String output = outputFuture.get();
      if (process.exitValue() != 0) {
        throw new PipelineException("Pipeline failed with exit code " + process.exitValue() + ":\n" + output);
      }
      return parseOutput(output, previewPath(projectRoot, imagePath));
    } catch (IOException e) {
      throw new PipelineException("Cannot start Python pipeline. Check MAIL_OCR_PYTHON and project path.", e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new PipelineException("Pipeline execution was interrupted.", e);
    } catch (ExecutionException e) {
      throw new PipelineException("Cannot read pipeline output.", e);
    }
  }

  public String export(Map<String, Object> fields, boolean sendSheet, boolean sendEmail) {
    Path projectRoot = Path.of(properties.getProjectRoot()).toAbsolutePath().normalize();
    Path uploadDir = projectRoot.resolve(properties.getUploadDir()).normalize();
    try {
      Files.createDirectories(uploadDir);
      Path jsonFile = uploadDir.resolve("export-" + UUID.randomUUID() + ".json");
      objectMapper.writeValue(jsonFile.toFile(), fields);

      List<String> command = new ArrayList<>();
      command.add(resolve(projectRoot, properties.getPythonExecutable()).toString());
      command.add("-X");
      command.add("utf8");
      command.add("src/export_from_json.py");
      command.add(jsonFile.toAbsolutePath().normalize().toString());
      if (!sendSheet) {
        command.add("--no_sheet");
      }
      if (!sendEmail) {
        command.add("--no_email");
      }
      return runCommand(projectRoot, command);
    } catch (IOException e) {
      throw new PipelineException("Cannot export shipment fields.", e);
    }
  }

  private PipelineResult parseOutput(String output, Path previewImagePath) {
    int start = output.indexOf('{');
    int end = output.lastIndexOf('}');
    if (start < 0 || end <= start) {
      throw new PipelineException("Pipeline did not return a JSON object:\n" + output);
    }
    String json = output.substring(start, end + 1);
    try {
      Map<String, Object> fields = objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
      boolean needReview = output.contains("need_review=True")
          || "YES".equalsIgnoreCase(String.valueOf(fields.getOrDefault("need_review", "")));
      return new PipelineResult(fields, needReview, output, previewImagePath);
    } catch (IOException e) {
      throw new PipelineException("Cannot parse pipeline JSON:\n" + output, e);
    }
  }

  private static boolean isSupportedBackend(String value) {
    return "easyocr".equals(value) || "vietocr".equals(value) || "paddleocr".equals(value);
  }

  private static Path resolve(Path projectRoot, String value) {
    Path path = Path.of(value);
    return path.isAbsolute() ? path : projectRoot.resolve(path).normalize();
  }

  private Path previewPath(Path projectRoot, Path imagePath) {
    String fileName = imagePath.getFileName().toString();
    int dot = fileName.lastIndexOf('.');
    String stem = dot > 0 ? fileName.substring(0, dot) : fileName;
    Path outputDir = resolve(projectRoot, properties.getOutputDir());
    return outputDir.resolve(stem + "_preview.jpg").normalize();
  }

  private String runCommand(Path projectRoot, List<String> command) {
    ProcessBuilder builder = new ProcessBuilder(command);
    builder.directory(projectRoot.toFile());
    builder.redirectErrorStream(true);

    try {
      Process process = builder.start();
      CompletableFuture<String> outputFuture = CompletableFuture.supplyAsync(() -> {
        try {
          return new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
          throw new PipelineException("Cannot read command output.", e);
        }
      });
      boolean finished = process.waitFor(TIMEOUT.toSeconds(), TimeUnit.SECONDS);
      if (!finished) {
        process.destroyForcibly();
        throw new PipelineException("Command timed out after " + TIMEOUT.toMinutes() + " minutes.");
      }
      String output = outputFuture.get();
      if (process.exitValue() != 0) {
        throw new PipelineException("Command failed with exit code " + process.exitValue() + ":\n" + output);
      }
      return output;
    } catch (IOException e) {
      throw new PipelineException("Cannot start command.", e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new PipelineException("Command execution was interrupted.", e);
    } catch (ExecutionException e) {
      throw new PipelineException("Cannot read command output.", e);
    }
  }
}
