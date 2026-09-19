package xiaozhi.modules.hardware.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.hardware.dto.HardwareLifecycleRequests;
import xiaozhi.modules.hardware.service.HardwareLifecycleService;

@RestController
@RequestMapping("/hardware/lifecycle")
@RequiredArgsConstructor
public class HardwareLifecycleController {
    private final HardwareLifecycleService service;
    @PostMapping("/verify") public Result<Map<String,Object>> verify(@Valid @RequestBody HardwareLifecycleRequests.Verify body) {
        return new Result<Map<String,Object>>().ok(service.verify(body));
    }
    @PostMapping("/activate") public Result<Map<String,Object>> activate(@Valid @RequestBody HardwareLifecycleRequests.Activate body) {
        return new Result<Map<String,Object>>().ok(service.activate(body));
    }
    @PostMapping("/unbind") public Result<Map<String,Object>> unbind(@Valid @RequestBody HardwareLifecycleRequests.Unbind body) {
        return new Result<Map<String,Object>>().ok(service.unbind(body));
    }
}
