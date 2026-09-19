package xiaozhi.modules.account.controller;

import java.util.List;
import java.util.Map;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.service.AccountAuthService;
import xiaozhi.modules.account.service.AccountService;
import xiaozhi.modules.security.user.SecurityUser;

@Validated
@RestController
@RequestMapping("/account")
@RequiredArgsConstructor
public class AccountController {
    private final AccountService service;
    private final AccountAuthService authService;
    private long id() { return SecurityUser.getUserId(); }

    @GetMapping("/profile") public Result<Map<String,Object>> profile() { return new Result<Map<String,Object>>().ok(service.profile(id())); }
    @PutMapping("/profile") public Result<Void> profile(@RequestBody AccountRequests.Profile p) { service.updateProfile(id(), p); return new Result<>(); }
    @GetMapping("/privacy") public Result<Map<String,Object>> privacy() { return new Result<Map<String,Object>>().ok(service.privacy(id())); }
    @PutMapping("/privacy") public Result<Void> privacy(@RequestBody AccountRequests.Privacy p) { service.updatePrivacy(id(), p); return new Result<>(); }
    @PutMapping("/combination") public Result<Void> combination(@Valid @RequestBody AccountRequests.CombinationChange p) { authService.changeCombination(id(), p); return new Result<>(); }
    @PutMapping("/guardian-pin") public Result<Void> pin(@Valid @RequestBody AccountRequests.GuardianPin p) { service.setPin(id(), p); return new Result<>(); }
    @PostMapping("/guardian-pin/verify") public Result<Map<String,Object>> verifyPin(@Valid @RequestBody AccountRequests.GuardianPin p) { return new Result<Map<String,Object>>().ok(service.verifyPin(id(), p)); }

    @GetMapping("/household/members") public Result<List<Map<String,Object>>> members() { return new Result<List<Map<String,Object>>>().ok(service.members(id())); }
    @PostMapping("/household/members") public Result<Map<String,Object>> addMember(@RequestBody AccountRequests.Member p) { return new Result<Map<String,Object>>().ok(service.addMember(id(), p)); }
    @PutMapping("/household/members/{memberId}") public Result<Void> updateMember(@PathVariable String memberId, @RequestBody AccountRequests.Member p) { service.updateMember(id(), memberId, p); return new Result<>(); }
    @DeleteMapping("/household/members/{memberId}") public Result<Void> removeMember(@PathVariable String memberId) { service.removeMember(id(), memberId); return new Result<>(); }

    @GetMapping("/voice-profiles") public Result<List<Map<String,Object>>> voiceProfiles() { return new Result<List<Map<String,Object>>>().ok(service.voiceProfiles(id())); }
    @PostMapping("/voice-profiles") public Result<Map<String,Object>> createVoiceProfile(@Valid @RequestBody AccountRequests.VoiceProfile p) { return new Result<Map<String,Object>>().ok(service.createVoiceProfile(id(), p)); }
    @DeleteMapping("/voice-profiles/{profileId}") public Result<Void> revokeVoiceProfile(@PathVariable String profileId) { service.revokeVoiceProfile(id(), profileId); return new Result<>(); }

    @PostMapping("/phone-change") public Result<Map<String,Object>> startPhone(@Valid @RequestBody AccountRequests.PhoneChangeStart p) { return new Result<Map<String,Object>>().ok(service.startPhoneChange(id(), p)); }
    @PostMapping("/phone-change/complete") public Result<Void> completePhone(@Valid @RequestBody AccountRequests.PhoneChangeComplete p) { service.completePhoneChange(id(), p); return new Result<>(); }

    @GetMapping("/devices") public Result<List<Map<String,Object>>> devices() { return new Result<List<Map<String,Object>>>().ok(service.devices(id())); }
    @PostMapping("/devices/bind") public Result<Void> bind(@Valid @RequestBody AccountRequests.DeviceBind p) { service.bindDevice(id(), p); return new Result<>(); }
    @DeleteMapping("/devices/{deviceId}") public Result<Void> unbind(@PathVariable String deviceId) { service.unbindDevice(id(), deviceId); return new Result<>(); }

    @PostMapping("/deletion") public Result<Map<String,Object>> delete(@Valid @RequestBody AccountRequests.Deletion p) { return new Result<Map<String,Object>>().ok(service.requestDeletion(id(), p)); }
    @DeleteMapping("/deletion") public Result<Void> cancelDeletion() { service.cancelDeletion(id()); return new Result<>(); }
}
