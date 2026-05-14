package com.mailocr.api.repository;

import com.mailocr.api.model.Shipment;
import com.mailocr.api.model.ShipmentStatus;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ShipmentRepository extends MongoRepository<Shipment, String> {
  List<Shipment> findTop30ByOrderByCreatedAtDesc();

  List<Shipment> findByStatusOrderByCreatedAtDesc(ShipmentStatus status);
}
