package xiaozhi.modules.hardware.service;

import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.account.repository.AccountRepository;
import xiaozhi.modules.agent.dto.AgentCreateDTO;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.hardware.dto.HardwareLifecycleRequests;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.sys.dto.SysUserDTO;

@Service
@RequiredArgsConstructor
public class HardwareLifecycleService {
    private final JdbcTemplate jdbc;
    private final SysUserTokenService tokenService;
    private final AgentService agentService;
    private final DeviceService deviceService;
    private final AgentChatHistoryService chatHistoryService;
    private final AccountRepository accountRepository;

    public Map<String,Object> verify(HardwareLifecycleRequests.Verify request) {
        String mac = normalizeMac(request.macAddress());
        List<Map<String,Object>> rows = jdbc.queryForList(
                "SELECT product_code,serial_number,mac_address,board,status FROM hardware_product_unit WHERE product_code=? AND serial_number=? AND mac_address=?",
                request.productCode(), request.serialNumber(), mac);
        if (rows.isEmpty()) throw new RenException(ErrorCode.HARDWARE_NOT_OURS);
        String status = String.valueOf(rows.getFirst().get("status"));
        if ("REVOKED".equals(status) || "SCRAPPED".equals(status)) throw new RenException(ErrorCode.HARDWARE_REVOKED);
        return Map.of("verified", true, "status", status, "macAddress", mac);
    }

    @Transactional
    public Map<String,Object> activate(HardwareLifecycleRequests.Activate request) {
        SysUserDTO account = account(request.accountToken());
        assertNewRequest(request.requestId());
        String mac = normalizeMac(request.macAddress());
        Map<String,Object> hardware = lockHardware(request.productCode(), request.serialNumber(), mac);
        long hardwareId = ((Number) hardware.get("id")).longValue();
        String status = String.valueOf(hardware.get("status"));
        if ("REVOKED".equals(status) || "SCRAPPED".equals(status)) throw new RenException(ErrorCode.HARDWARE_REVOKED);
        if ("ACTIVATED".equals(status)) {
            Number owner = (Number) hardware.get("activated_account_id");
            if (owner != null && owner.longValue() == account.getId()) {
                return Map.of("agentId", String.valueOf(hardware.get("activated_agent_id")),
                        "macAddress", mac, "status", "ALREADY_ACTIVATED");
            }
            throw new RenException(ErrorCode.HARDWARE_ALREADY_ACTIVATED);
        }

        AgentCreateDTO agent = new AgentCreateDTO();
        String suffix = request.serialNumber().substring(Math.max(0, request.serialNumber().length() - 6));
        agent.setAgentName(request.agentName() == null || request.agentName().isBlank() ? "小伴-" + suffix : request.agentName());
        String agentId = agentService.createAgentForUser(agent, account.getId());
        deviceService.deviceActivationForUser(agentId, request.activationCode(), account.getId(), mac);
        DeviceEntity saved = deviceService.getDeviceByMacAddress(mac);
        accountRepository.bindingHistory(saved.getId(), account.getId(), mac, "SIGNED_QR");
        int changed = jdbc.update("UPDATE hardware_product_unit SET status='ACTIVATED',activated_account_id=?,activated_agent_id=?,activated_at=NOW() WHERE id=? AND status='PROVISIONED'",
                account.getId(), agentId, hardwareId);
        if (changed != 1) throw new RenException(ErrorCode.HARDWARE_ALREADY_ACTIVATED);
        event(hardwareId, account.getId(), agentId, request.requestId(), "ACTIVATE", "SUCCESS", null);
        return Map.of("agentId", agentId, "deviceId", saved.getId(), "macAddress", mac, "status", "ACTIVATED");
    }

    @Transactional
    public Map<String,Object> unbind(HardwareLifecycleRequests.Unbind request) {
        if (!"UNBIND".equals(request.confirmation())) throw new RenException(ErrorCode.HARDWARE_UNBIND_INVALID);
        SysUserDTO account = account(request.accountToken());
        assertNewRequest(request.requestId());
        String mac = normalizeMac(request.macAddress());
        List<Map<String,Object>> units = jdbc.queryForList("SELECT * FROM hardware_product_unit WHERE mac_address=? FOR UPDATE", mac);
        if (units.isEmpty()) throw new RenException(ErrorCode.HARDWARE_NOT_OURS);
        Map<String,Object> hardware = units.getFirst();
        Number owner = (Number) hardware.get("activated_account_id");
        if (!"ACTIVATED".equals(hardware.get("status")) || owner == null || owner.longValue() != account.getId())
            throw new RenException(ErrorCode.HARDWARE_UNBIND_INVALID);
        DeviceEntity device = deviceService.getDeviceByMacAddress(mac);
        if (device == null || !account.getId().equals(device.getUserId())) throw new RenException(ErrorCode.HARDWARE_UNBIND_INVALID);
        String agentId = device.getAgentId();

        chatHistoryService.deleteByAgentId(agentId, true, true);
        jdbc.update("DELETE FROM memory_profile WHERE mac_address=?", mac);
        jdbc.update("DELETE FROM member_profile WHERE mac_address=?", mac);
        jdbc.update("DELETE FROM ai_agent_voice_print WHERE agent_id=?", agentId);
        jdbc.update("DELETE FROM ai_agent_plugin_mapping WHERE agent_id=?", agentId);
        jdbc.update("DELETE FROM ai_agent_context_provider WHERE agent_id=?", agentId);
        jdbc.update("DELETE FROM ai_agent_correct_word_mapping WHERE agent_id=?", agentId);
        jdbc.update("DELETE FROM ai_agent_tag_relation WHERE agent_id=?", agentId);
        accountRepository.unbindingHistory(device.getId(), account.getId());
        deviceService.unbindDevice(account.getId(), device.getId());
        agentService.deleteById(agentId);
        long hardwareId = ((Number) hardware.get("id")).longValue();
        jdbc.update("UPDATE hardware_product_unit SET status='PROVISIONED',activated_account_id=NULL,activated_agent_id=NULL,activated_at=NULL,last_unbound_at=NOW() WHERE id=?", hardwareId);
        event(hardwareId, account.getId(), agentId, request.requestId(), "UNBIND", "SUCCESS", "personal data purged");
        return Map.of("macAddress", mac, "agentId", agentId, "memoryKey", mac, "status", "UNBOUND");
    }

    private SysUserDTO account(String token) {
        SysUserDTO account = tokenService.getUserByToken(token);
        if (account == null || account.getId() == null) throw new RenException(ErrorCode.TOKEN_INVALID);
        return account;
    }
    private Map<String,Object> lockHardware(String productCode, String serial, String mac) {
        List<Map<String,Object>> rows = jdbc.queryForList("SELECT * FROM hardware_product_unit WHERE product_code=? AND serial_number=? AND mac_address=? FOR UPDATE", productCode, serial, mac);
        if (rows.isEmpty()) throw new RenException(ErrorCode.HARDWARE_NOT_OURS);
        return rows.getFirst();
    }
    private void assertNewRequest(String requestId) {
        Integer count = jdbc.queryForObject("SELECT COUNT(*) FROM hardware_lifecycle_event WHERE request_id=?", Integer.class, requestId);
        if (count != null && count > 0) throw new RenException(ErrorCode.HARDWARE_REQUEST_DUPLICATE);
    }
    private void event(long hardwareId, long accountId, String agentId, String requestId, String type, String result, String detail) {
        jdbc.update("INSERT INTO hardware_lifecycle_event(hardware_id,account_id,agent_id,event_type,request_id,result,detail) VALUES(?,?,?,?,?,?,?)",
                hardwareId, accountId, agentId, type, requestId, result, detail);
    }
    public static String normalizeMac(String value) {
        String hex = value == null ? "" : value.replaceAll("[^0-9A-Fa-f]", "").toLowerCase(Locale.ROOT);
        if (!hex.matches("[0-9a-f]{12}")) throw new RenException(ErrorCode.HARDWARE_ACTIVATION_INVALID);
        return hex.replaceAll("(..)(?!$)", "$1:");
    }
}
