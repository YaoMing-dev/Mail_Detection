package com.mailocr.api.service;

import java.util.Map;
import java.nio.file.Path;
import java.util.LinkedHashMap;

public record PipelineResult(Map<String, Object> fields, boolean needReview, String rawOutput, Path previewImagePath) {
  public PipelineResult {
    fields = fields == null ? new LinkedHashMap<>() : fields;
  }
}
