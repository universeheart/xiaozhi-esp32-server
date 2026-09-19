package xiaozhi.modules.hardware.dto;

import jakarta.validation.constraints.NotBlank;

public final class HardwareLifecycleRequests {
    private HardwareLifecycleRequests() {}
    public record Verify(@NotBlank String productCode, @NotBlank String serialNumber,
            @NotBlank String macAddress) {}
    public record Activate(@NotBlank String requestId, @NotBlank String accountToken,
            @NotBlank String productCode, @NotBlank String serialNumber, @NotBlank String macAddress,
            @NotBlank String activationCode, String board, String appVersion, String agentName) {}
    public record Unbind(@NotBlank String requestId, @NotBlank String accountToken,
            @NotBlank String macAddress, @NotBlank String confirmation) {}
}
