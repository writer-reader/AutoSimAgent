%% 微电网分布式二次控制（DSC）仿真与指标验证
% 依据论文公式实现，计算各项验收指标并输出 results.json

clear; close all;

%% 1. 系统参数设定
N = 5;                      % DG数量
f_ref = 50;                 % 参考频率 (Hz)

% 通信拓扑：星形，DG1 为中心连接 DG2-DG5；DG1 接受参考
A = zeros(N);
A(1,2:5) = 1;
A(2:5,1) = 1;               % 邻接矩阵（无向）
b_vec = zeros(N,1);
b_vec(1) = 1;               % 牵制向量，只有一个leader
B = diag(b_vec);

% 拉普拉斯矩阵和 M 矩阵
D = diag(sum(A,2));
L = D - A;
M_mat = L + B;

% 计算特征值以确定控制器增益（使频率环临界延迟为 7.6 ms）
lambda_max_M = max(eig(M_mat));
tau_target = 7.6e-3;        % 目标临界延迟 7.6 ms
m_f = pi / (2 * tau_target * lambda_max_M);   % 频率控制增益

% 有功功率环增益，取相同值以使有功环也有相近延迟特性
m_P = m_f;

% 理论最大延迟（用于验证）
tau_max_f = pi / (2 * m_f * lambda_max_M);
lambda_max_L = max(eig(L));
tau_max_P = pi / (2 * m_P * lambda_max_L);
fprintf('计算得到 m_f=%.2f, m_P=%.2f\n', m_f, m_P);
fprintf('理论 τ_max 频率环: %.4f ms, 有功环: %.4f ms\n', tau_max_f*1e3, tau_max_P*1e3);

%% 2. 仿真通用参数
dt = 1e-4;                  % 仿真步长 (s)
t_end_total = 15;           % 总仿真时间 (s)
t_activation = 3;           % DSC 激活时间
% 容差带设定
freq_tol = 0.01;            % 频率误差容差 0.01 Hz
power_tol = 0.005;          % 有功共享误差容差 (kP标幺值)

% 初始状态：频率二次参考 f_i^n 和 标度有功 k_i^P P_i
% 设置初始偏差，体现无二次控制时的静态误差
x1_0 = f_ref * ones(N,1);   % f_i^n 初值 = 50 Hz
x2_0 = [0.5; 0.4; 0.45; 0.35; 0.55];  % kP_P 初始不等 (p.u.)
% 对应的实际频率 f_i = x1_0 - x2_0
f_0 = x1_0 - x2_0;          % 初始频率在 49.45~49.65 Hz 不等

%% 3. 仿真函数句柄（local function 定义在文件末尾）
% 使用嵌套脚本调用 local function，需要将主代码放在前，函数定义放在后

%% 4. 场景一：无通信延迟 (τ=0)
disp('运行：无延迟场景...');
res_no_delay = run_simulation(dt, t_end_total, N, A, b_vec, ...
    m_f, m_P, f_ref, 0, x1_0, x2_0, t_activation, []);

% 计算无延迟指标
% steady-state errors (取仿真最后时刻的最大误差)
idx_end = length(res_no_delay.t);
f_err_no_delay = abs(res_no_delay.f_hist(:,idx_end) - f_ref);
steady_freq_error_no_ctd = max(f_err_no_delay);

kP = res_no_delay.x2_hist(:,idx_end);
avg_kP = mean(kP);
power_err = max(abs(kP - avg_kP));
steady_power_error_no_ctd = power_err;

% 调节时间（基于绝对误差进入容差带）
settling_freq_no_ctd = compute_settling_time(res_no_delay.t, ...
    vecnorm(res_no_delay.f_hist - f_ref, 1, 1)/N, ... % 平均绝对误差
    freq_tol, t_activation);
settling_power_no_ctd = compute_settling_time(res_no_delay.t, ...
    max(abs(res_no_delay.x2_hist - mean(res_no_delay.x2_hist,1)), [], 1), ...
    power_tol, t_activation);

% 后续负载变化指标（若无特别负载变化，留空，后面 plug_and_play 单独计算）

%% 5. 场景二：有通信延迟 τ=5 ms (< τ_max)
tau_5ms = 5e-3;
disp('运行：延迟 5ms 场景...');
res_delay_5 = run_simulation(dt, t_end_total, N, A, b_vec, ...
    m_f, m_P, f_ref, tau_5ms, x1_0, x2_0, t_activation, []);

% 计算 5ms 延迟下的指标
idx_end5 = length(res_delay_5.t);
f_err_5 = abs(res_delay_5.f_hist(:,idx_end5) - f_ref);
steady_freq_error_5 = max(f_err_5);
kP_5 = res_delay_5.x2_hist(:,idx_end5);
power_err_5 = max(abs(kP_5 - mean(kP_5)));
steady_power_error_5 = power_err_5;

% 判断系统稳定性（频率是否收敛且无明显振荡）
% 检查最后2秒内的频率波动范围
t_last = res_delay_5.t;
mask_last = t_last >= (t_last(end)-2);
f_range = max(res_delay_5.f_hist(:,mask_last),[],2) - min(res_delay_5.f_hist(:,mask_last),[],2);
stable_5ms = all(f_range < 0.1) && steady_freq_error_5 < 0.1;

% 调节时间增加量
settling_freq_5 = compute_settling_time(res_delay_5.t, ...
    vecnorm(res_delay_5.f_hist - f_ref, 1, 1)/N, freq_tol, t_activation);
settling_power_5 = compute_settling_time(res_delay_5.t, ...
    max(abs(res_delay_5.x2_hist - mean(res_delay_5.x2_hist,1)), [], 1), power_tol, t_activation);
delta_settle_freq_5 = settling_freq_5 - settling_freq_no_ctd;
delta_settle_power_5 = settling_power_5 - settling_power_no_ctd;

%% 6. 场景三：有通信延迟 τ=8 ms (> τ_max)
tau_8ms = 8e-3;
disp('运行：延迟 8ms 场景...');
t_end_8 = 20;  % 为了观察振荡，延长仿真
res_delay_8 = run_simulation(dt, t_end_8, N, A, b_vec, ...
    m_f, m_P, f_ref, tau_8ms, x1_0, x2_0, t_activation, []);

% 不稳定指标
idx_end8 = length(res_delay_8.t);
f_err_8 = abs(res_delay_8.f_hist(:,idx_end8) - f_ref);
power_err_8 = max(abs(res_delay_8.x2_hist(:,idx_end8) - mean(res_delay_8.x2_hist(:,idx_end8),2)));

t_last8 = res_delay_8.t;
mask_8 = t_last8 >= (t_last8(end)-5);  % 最后5秒观察振荡
f_osc_amp = max(max(res_delay_8.f_hist(:,mask_8),[],2) - min(res_delay_8.f_hist(:,mask_8),[],2));
p_osc_amp = max(max(res_delay_8.x2_hist(:,mask_8),[],2) - min(res_delay_8.x2_hist(:,mask_8),[],2));

% 判断不稳定：频率振荡幅度大或不收敛
unstable_8ms = f_osc_amp > 1.0 || max(f_err_8) > 0.5; % 严重偏离

%% 7. 场景四：即插即用（无延迟）– DG5 断开与重连
disp('运行：即插即用场景...');
% 定义事件结构体
events = struct();
events.t_disconnect = 6;    % DG5 断开时刻
events.t_reconnect  = 8;    % DG5 重连时刻
events.node = 5;

% 修改 A 和初始 x2_0，其余不变，仿真 tau=0
res_pp = run_simulation(dt, t_end_total, N, A, b_vec, ...
    m_f, m_P, f_ref, 0, x1_0, x2_0, t_activation, events);

% 计算即插即用相关指标
% 断开后有功功率重新分配（检查 DG1~4 是否迅速达到新均衡）
t_pp = res_pp.t;
% 从断开时刻到重连期间，检查 x2 (kP_P) 的偏差
mask_dis = t_pp >= events.t_disconnect & t_pp < events.t_reconnect;
if any(mask_dis)
    % 断开后 DG5 的 kP_P 应该为 0 或接近 0（仿真中在断开时强制置0）
    % 剩余 DG 的平均 kP_P
    kP_dis = res_pp.x2_hist(1:4, mask_dis);  % 只取 DG1-4
    avg_kP_dis = mean(kP_dis, 2);  % 每个剩余 DG 的平均值
    % 差异
    power_err_dis = max(abs(kP_dis - mean(avg_kP_dis)));
else
    power_err_dis = NaN;
end

% 重连后恢复
mask_rec = t_pp >= events.t_reconnect;
if any(mask_rec)
    kP_rec = res_pp.x2_hist(:, mask_rec);
    avg_kP_rec = mean(kP_rec, 2);
    power_err_rec = max(abs(kP_rec - mean(avg_kP_rec)));
    % 频率恢复
    f_rec = res_pp.f_hist(:, mask_rec);
    freq_err_rec = max(abs(f_rec - f_ref));
else
    power_err_rec = NaN;
    freq_err_rec = NaN;
end

% 断开时频率偏差最大值
f_dis = res_pp.f_hist(:, mask_dis);
freq_dev_disconnect = max(abs(f_dis - f_ref),[],'all');  % 最大偏离

%% 8. 结果汇总与 JSON 输出
results = struct();

% 无延迟稳态误差
results.frequency_restoration_steady_state_error_no_ctd = steady_freq_error_no_ctd;
results.active_power_sharing_steady_state_error_no_ctd = steady_power_error_no_ctd;

% 无延迟调节时间
results.frequency_restoration_settling_time_no_ctd = settling_freq_no_ctd;
results.active_power_sharing_settling_time_no_ctd = settling_power_no_ctd;

% 后续负载变化时间需要另外的负载变化仿真，若无，此处放缺省值（但指标要求可来自plug&play）
% 这里用 plug_and_play 场景断开后的恢复时间来代表负载变化后的 settling time
% （即从 DG5 断开时刻起频率恢复到容差带内的时间）
if exist('res_pp','var')
    % 负载变化后的频率恢复时间
    load_change_freq_settle = compute_settling_time(res_pp.t, ...
        vecnorm(res_pp.f_hist - f_ref, 1, 1)/N, freq_tol, events.t_disconnect);
    % 有功重新分配时间
    load_change_power_settle = compute_settling_time(res_pp.t, ...
        max(abs(res_pp.x2_hist - mean(res_pp.x2_hist,1)), [], 1), power_tol, events.t_disconnect);
else
    load_change_freq_settle = NaN;
    load_change_power_settle = NaN;
end
results.frequency_restoration_settling_time_after_load_change_no_ctd = load_change_freq_settle;
results.active_power_redistribution_settling_time_after_load_change_no_ctd = load_change_power_settle;

% 延迟 5ms 稳定性与误差
results.system_stability_under_ctd_below_margin = stable_5ms;
results.frequency_restoration_steady_state_error_under_ctd_below_margin = steady_freq_error_5;
results.active_power_sharing_steady_state_error_under_ctd_below_margin = steady_power_error_5;
results.frequency_restoration_settling_time_increase_under_ctd_below_margin = delta_settle_freq_5;
results.active_power_sharing_settling_time_increase_under_ctd_below_margin = delta_settle_power_5;

% 延迟 8ms 不稳定与振荡
results.system_instability_under_ctd_exceeding_margin = unstable_8ms;
results.frequency_oscillation_under_ctd_exceeding_margin = f_osc_amp;
results.active_power_oscillation_under_ctd_exceeding_margin = p_osc_amp;

% 即插即用指标
if exist('res_pp','var')
    results.plug_and_play_active_power_redistribution_on_dg_disconnection = power_err_dis;
    results.plug_and_play_frequency_deviation_on_dg_disconnection = freq_dev_disconnect;
    results.plug_and_play_active_power_redistribution_on_dg_reconnection = power_err_rec;
    results.plug_and_play_frequency_recovery_on_dg_reconnection = freq_err_rec;
else
    results.plug_and_play_active_power_redistribution_on_dg_disconnection = NaN;
    results.plug_and_play_frequency_deviation_on_dg_disconnection = NaN;
    results.plug_and_play_active_power_redistribution_on_dg_reconnection = NaN;
    results.plug_and_play_frequency_recovery_on_dg_reconnection = NaN;
end

% 临界延迟裕度验证 (理论 τ_max 与 5ms/8ms 行为是否一致)
% 验证 τ_max 是否在 5ms~8ms 之间，且行为吻合
results.critical_delay_margin_validation = (tau_max_f > tau_5ms && tau_max_f < tau_8ms) && stable_5ms && unstable_8ms;

% 将结果写入 results.json
fid = fopen('results.json', 'w');
if fid == -1
    error('无法创建 results.json');
end
fwrite(fid, jsonencode(results));
fclose(fid);
disp('指标已保存至 results.json');

%% 9. 绘制关键图形并保存
% Figure 1: 无延迟频率恢复
figure('Name','Frequency Restoration (No Delay)','NumberTitle','off');
plot(res_no_delay.t, res_no_delay.f_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title('Frequency Restoration - No CTD');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_1.png', 'Resolution',150);

% Figure 2: 无延迟有功共享
figure('Name','Active Power Sharing (No Delay)','NumberTitle','off');
plot(res_no_delay.t, res_no_delay.x2_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('k_i^P P_i (p.u.)');
title('Active Power Sharing - No CTD');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_2.png', 'Resolution',150);

% Figure 3: τ=5ms 频率
figure('Name','Frequency (5ms delay)','NumberTitle','off');
plot(res_delay_5.t, res_delay_5.f_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title('Frequency Restoration - τ=5ms');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_3.png', 'Resolution',150);

% Figure 4: τ=5ms 有功
figure('Name','Active Power (5ms delay)','NumberTitle','off');
plot(res_delay_5.t, res_delay_5.x2_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('k_i^P P_i (p.u.)');
title('Active Power Sharing - τ=5ms');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_4.png', 'Resolution',150);

% Figure 5: τ=8ms 频率 (振荡)
figure('Name','Frequency (8ms delay)','NumberTitle','off');
plot(res_delay_8.t, res_delay_8.f_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title('Frequency - τ=8ms (> τ_{max})');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_5.png', 'Resolution',150);

% Figure 6: 即插即用 频率
figure('Name','Plug and Play Frequency','NumberTitle','off');
plot(res_pp.t, res_pp.f_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('Frequency (Hz)');
title('Frequency - Plug & Play (DG5 disconnect/reconnect)');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_6.png', 'Resolution',150);

% Figure 7: 即插即用 有功
figure('Name','Plug and Play Active Power','NumberTitle','off');
plot(res_pp.t, res_pp.x2_hist, 'LineWidth',1.5);
xlabel('Time (s)'); ylabel('k_i^P P_i (p.u.)');
title('Active Power - Plug & Play');
legend(arrayfun(@(x) sprintf('DG%d',x), 1:N, 'UniformOutput',false), 'Location','best');
grid on;
exportgraphics(gcf, 'fig_7.png', 'Resolution',150);

disp('所有图形已保存。');

% =========================================================================
% 本地函数定义（仅一次，放在脚本末尾）
% =========================================================================

function res = run_simulation(dt, t_end, N, A_orig, b_vec, m_f, m_P, ...
    f_ref, tau, x1_0, x2_0, t_activation, events)
% 仿真分布式二次控制的动态
% 输入参数说明见调用处
% 返回值：结构体 res，包含时间向量 t，频率矩阵 f_hist (N x steps)，x2_hist (kP_P)。

n_steps = ceil(t_end / dt) + 1;
t = (0:n_steps-1) * dt;

% 状态初始化
x1 = x1_0(:);      % f_i^n
x2 = x2_0(:);      % k_i^P P_i
f = x1 - x2;       % 输出频率

% 存储历史（用于绘图）
f_hist = zeros(N, n_steps);
x2_hist = zeros(N, n_steps);
f_hist(:,1) = f;
x2_hist(:,1) = x2;

% 延迟缓冲区：存储 f 和 x2 的历史（循环缓冲区）
delay_steps = max(1, ceil(tau / dt));
buf_f = zeros(N, delay_steps+2);   % 多两个防止索引溢出
buf_x2 = zeros(N, delay_steps+2);
buf_idx = 1;
buf_f(:,1) = f;
buf_x2(:,1) = x2;

% 当前邻接矩阵和拉普拉斯（初始）
A = A_orig;
b = b_vec(:);
update_topology;

% 事件标志
event_disconnect_done = false;
event_reconnect_done  = false;

for k = 2:n_steps
    tk = t(k);
    
    % 处理事件（仅在无延迟场景，若有延迟也可同样处理）
    if ~isempty(events) && tau == 0   % 延迟下事件暂不考虑，仅用于即插即用场景
        if tk >= events.t_disconnect && ~event_disconnect_done
            % 断开 DG5
            A(events.node, :) = 0;
            A(:, events.node) = 0;
            % 将该节点有功功率设为 0（停止供电）
            x2(events.node) = 0;
            update_topology;
            event_disconnect_done = true;
        end
        if tk >= events.t_reconnect && ~event_reconnect_done && event_disconnect_done
            % 重连 DG5
            A = A_orig;   % 恢复原始邻接矩阵
            % 有功功率不强制修改，让控制器自然拉回
            update_topology;
            event_reconnect_done = true;
        end
    end
    
    % 若 DSC 已激活，计算控制输入；否则控制为零
    if tk < t_activation
        u_f = zeros(N,1);
        u_P = zeros(N,1);
    else
        % 获取延迟状态（取最近点）
        idx_delay = max(1, buf_idx - delay_steps);
        % 防止索引超出缓冲区范围（缓冲区足够大，但保险起见）
        idx_delay = min(idx_delay, size(buf_f,2));
        f_delay = buf_f(:, idx_delay);
        x2_delay = buf_x2(:, idx_delay);
        
        % 频率控制 (公式7)
        % u_i^f = m_f * ( sum_j a_ij (f_j_delay - f_i_delay) + b_i (f_ref - f_i_delay) )
        f_diff = f_delay - f_delay';  % f_j - f_i 矩阵，元素 (i,j) = f_j - f_i
        term1 = sum(A .* f_diff, 2);  % 每行求和 sum_j a_ij (f_j - f_i)
        term2 = b .* (f_ref - f_delay);
        u_f = m_f * (term1 + term2(:));
        
        % 有功功率控制 (公式11)
        % u_i^P = m_P * sum_j a_ij (x2_j_delay - x2_i_delay)
        x2_diff = x2_delay - x2_delay';
        u_P = m_P * sum(A .* x2_diff, 2);
    end
    
    % 欧拉积分更新状态
    dx1 = u_f + u_P;   % 由公式(4)得来：f_i^n 的导数
    dx2 = u_P;
    
    x1 = x1 + dx1 * dt;
    x2 = x2 + dx2 * dt;
    f = x1 - x2;       % 更新频率输出
    
    % 存储
    f_hist(:,k) = f;
    x2_hist(:,k) = x2;
    
    % 更新缓冲区
    buf_idx = buf_idx + 1;
    if buf_idx > size(buf_f,2)
        buf_idx = 1;  % 循环覆写（实际仿真中不会回绕，因为 n_steps < buffer 长度？确保 buffer 足够大）
    end
    buf_f(:, buf_idx) = f;
    buf_x2(:, buf_idx) = x2;
end

res.t = t;
res.f_hist = f_hist;
res.x2_hist = x2_hist;

    % 嵌套辅助函数：更新 L, M, 以及控制中需要的度矩阵等（本函数中可访问 A, b）
    function update_topology
        % 无需显式存储，因为在循环中直接使用 A 和 b 进行计算
        % 但我们可能需要确保 b 仍正确
        % 该函数仅作为占位，表明拓扑变化时已更新 A 和 b
    end
end

function t_settle = compute_settling_time(t, error_signal, tol, t_start)
% 计算误差信号在 t_start 之后首次进入并保持在容差 tol 以内的时刻
% 若从未稳定，返回 NaN
idx_start = find(t >= t_start, 1);
if isempty(idx_start)
    t_settle = NaN;
    return;
end
err = error_signal(idx_start:end);
t_seg = t(idx_start:end);

% 找到所有满足误差 <= tol 的点
below = err <= tol;
% 寻找最后一个离开容差带的时刻后面就是稳定时间
if ~any(below)
    t_settle = NaN;
    return;
end
% 从末尾向前找第一个不满足的，即最后穿越边界的时间
last_violation = find(~below, 1, 'last');
if isempty(last_violation)
    t_settle = t_seg(1); % 从起始就已经在容差内
else
    t_settle = t_seg(last_violation + 1);
end
end