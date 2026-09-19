package xiaozhi.modules.account.controller;

import java.util.Map;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.page.TokenDTO;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.account.dto.AccountRequests;
import xiaozhi.modules.account.service.AccountAuthService;

@Validated
@RestController
@RequestMapping("/account/auth")
@RequiredArgsConstructor
public class AccountAuthController {
    private final AccountAuthService service;

    @PostMapping("/status") public Result<Map<String, Object>> status(@Valid @RequestBody AccountRequests.Phone body) {
        return new Result<Map<String, Object>>().ok(service.status(body));
    }
    @PostMapping("/sms/send") public Result<Void> send(@Valid @RequestBody AccountRequests.SmsSend body) {
        service.send(body); return new Result<>();
    }
    @PostMapping("/sms/verify") public Result<Map<String, Object>> verify(@Valid @RequestBody AccountRequests.SmsVerify body) {
        return new Result<Map<String, Object>>().ok(service.verify(body));
    }
    @PostMapping("/register") public Result<TokenDTO> register(@Valid @RequestBody AccountRequests.Register body) {
        return service.register(body);
    }
    @PostMapping("/login/sms") public Result<TokenDTO> loginSms(@Valid @RequestBody AccountRequests.TicketLogin body) {
        return service.loginByTicket(body);
    }
    @PostMapping("/login/combination") public Result<TokenDTO> loginCombination(@Valid @RequestBody AccountRequests.CombinationLogin body) {
        return service.loginByCombination(body);
    }
}
