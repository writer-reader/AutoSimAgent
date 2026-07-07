%% 微电网分布式二次控制（DSC）仿真与指标验证
% 严格按照论文公式，使用固定控制器增益 m_f=50, m_P=50，
% 通过特征值分析计算理论延迟裕度，所有指标由模型正向计算。

clear; close all;

%% 1. 参数定义
N = 5;
f_ref = 50;                      % 参考频率 [Hz]

% 通信拓扑：星形，DG1为中心，连接DG2-DG5；DG1有参考信号
A = zeros(N);
A(1,2:5) = 1;
A(2:5,1) = 1;                   % 无向图
b_vec = zeros(N,1);
b_vec(1) = 1;

% 拉普拉斯矩阵与 M = L + B
D = diag(sum(A,2));
L = D - A;
B_mat = diag(b_vec);
M_mat = L + B_mat;

% 控制器增益（论文典型值）
m_f = 50;
m_P = 50;

% 理论延迟裕度（频率环与有功环分别计算，取小者为系统 tau_max）
lambda_max_M = max(eig(M_mat));
lambda_max_L = max(eig(L));
tau_max_f = pi / (2 * m_f * lambda_max_M);
tau_max_P = pi / (2 * m_P * lambda_max_L);
tau_max_sys = min(tau_max_f, tau_max_P);   % 系统临界延迟
fprintf('理论 tau_max (频率环): %.4f ms, (有功环): %.4f ms, 系统: %.4f ms\n', ...
    tau_max_f*1e3, tau_max_P*1e3, tau_max_sys*1e3);

%% 2. 仿真设置
dt = 1e-4;                       % 步长 [s]
t_end = 15;                      % 总仿真时间 [s]
t_activation = 3;                % DSC 激活时间 [s]

% 容差带
freq_tol = 0.01;                 % 频率稳态误差带 [Hz]
power_tol = 0.005;               % 有功共享误差带 (标幺值)

% 初始状态：假设 k_i^P = 1 对所有 i，则 x2 = P_i
% 初始有功不平衡，使 x2 初值不同
x2_0 = [0.5; 0.45; 0.4; 0.35; 0.5];  % P_i 初值
% 频率初始值由公式 f_i = f_ref - k_i^P P_i 给定 (设 f_i^n = f_ref 初始修正项为0)
x1_0 = f_ref - x2_0;             % 这样频率也有偏差

%% 3. 场景 1：无延迟，基本激活
disp('Scenario 1: No delay, basic activation...');
events = [];  % 无特殊事件
res_no_ctd = run_simulation(dt, t_end, N, A, b_vec, m_f, m_P, f_ref, 0, ...
    x1_0, x2_0, t_activation, events);

% 场景 2：无延迟，负载阶跃（在 t=6s 增加负荷）
disp('Scenario 2: No delay, load change at t=6s...');
events(1).time = 6.0;
events(1).type = 'load_step';
events(1).value = 0.05;         % 所有 x2 增加 0.05 模拟负荷突增
res_load_change = run_simulation(dt, t_end, N, A, b_vec, m_f, m_P, f_ref, 0, ...
    x1_0, x2_0, t_activation, events);

% 场景 3：无延迟，即插即用：DG5 在 t=6s 断开，t=8s 重连
disp('Scenario 3: No delay, plug-and-play DG5 disconnect/reconnect...');
events_pnp(1).time = 6.0;
events_pnp(1).type = 'dg_disconnect';
events_pnp(1).node = 5;
events_pnp(2).time = 8.0;
events_pnp(2).type = 'dg_reconnect';
events_pnp(2).node = 5;
res_pnp = run_simulation(dt, t_end, N, A, b_vec, m_f, m_P, f_ref, 0, ...
    x1_0, x2_0, t_activation, events_pnp);

% 场景 4：延迟 tau = 5 ms (< tau_max)
disp('Scenario 4: Delay 5 ms...');
tau_5 = 5e-3;
res_tau5 = run_simulation(dt, t_end, N, A, b_vec, m_f, m_P, f_ref, tau_5, ...
    x1_0, x2_0, t_activation, []);

% 场景 5：延迟 tau = 8 ms (> tau_max)
disp('Scenario 5: Delay 8 ms...');
tau_8 = 8e-3;
res_tau8 = run_simulation(dt, t_end, N, A, b_vec, m_f, m_P, f_ref, tau_8, ...
    x1_0, x2_0, t_activation, []);

%% 4. 计算各项指标
metrics = struct();  % 采用 containers.Map 后续写json，为方便这里用结构体暂存，但Key会超长，需转成map
idx_end = round(0.5/dt);  % 取最后0.5秒

% 辅助函数：计算稳态频率误差
calc_freq_ss = @(x1_mat,t_vec, ref_time) max(abs(mean(x1_mat(:, end-idx_end:end), 2) - f_ref));
% 辅助函数：计算稳态有功共享误差（所有节点与均值差的绝对值最大）
calc_power_ss = @(x2_mat,t_vec, ref_time) max(abs(mean(x2_mat(:, end-idx_end:end), 2) - mean(mean(x2_mat(:, end-idx_end:end), 2))));

% 辅助函数：计算 settling time（频率）
calc_settle_freq = @(x1_mat, t_vec, t0, tol) find_settling_time(x1_mat - f_ref, t_vec, t0, tol);
% 辅助函数：计算 settling time（有功共享）
calc_settle_power = @(x2_mat, t_vec, t0, tol) find_settling_time(x2_mat - mean(x2_mat,1), t_vec, t0, tol);

% 场景1：无延迟
freq_ss_1 = calc_freq_ss(res_no_ctd.x1_mat, res_no_ctd.t_vec, t_activation);
power_ss_1 = calc_power_ss(res_no_ctd.x2_mat, res_no_ctd.t_vec, t_activation);
settle_f_1 = calc_settle_freq(res_no_ctd.x1_mat, res_no_ctd.t_vec, t_activation, freq_tol);
settle_p_1 = calc_settle_power(res_no_ctd.x2_mat, res_no_ctd.t_vec, t_activation, power_tol);

% 场景2：负载变化后
settle_f_load = calc_settle_freq(res_load_change.x1_mat, res_load_change.t_vec, 6.0, freq_tol);
settle_p_load = calc_settle_power(res_load_change.x2_mat, res_load_change.t_vec, 6.0, power_tol);

% 场景4：tau=5ms
freq_ss_5 = calc_freq_ss(res_tau5.x1_mat, res_tau5.t_vec, t_activation);
power_ss_5 = calc_power_ss(res_tau5.x2_mat, res_tau5.t_vec, t_activation);
settle_f_5 = calc_settle_freq(res_tau5.x1_mat, res_tau5.t_vec, t_activation, freq_tol);
settle_p_5 = calc_settle_power(res_tau5.x2_mat, res_tau5.t_vec, t_activation, power_tol);

% 稳定性判断：最后一段的频率误差是否足够小
is_stable = @(x1_mat) max(abs(mean(x1_mat(:, end-idx_end:end),2) - f_ref)) < 1.0; % 粗略
stable_tau5 = is_stable(res_tau5.x1_mat);
stable_tau8 = is_stable(res_tau8.x1_mat);

% 场景5：tau=8ms 振荡指标
freq_osc = std(res_tau8.x1_mat(:, end-idx_end:end) - f_ref, 0, 'all');
power_osc = std(res_tau8.x2_mat(:, end-idx_end:end) - mean(res_tau8.x2_mat(:, end-idx_end:end),1), 0, 'all');

% 即插即用指标
% DG5断开后，频率最大偏差
t_dis = 6.0;
idx_dis = find(res_pnp.t_vec >= t_dis, 1);
freq_dev = max(abs(res_pnp.x1_mat(:, idx_dis:end) - f_ref), [], 'all');
% 有功重分配：在断开后2s内，有功共享误差能否收敛到容差
idx_after_dis = find(res_pnp.t_vec >= t_dis+2, 1);
if ~isempty(idx_after_dis)
    power_err_dis = max(abs(res_pnp.x2_mat(:, idx_after_dis:end) - mean(res_pnp.x2_mat(:, idx_after_dis:end),1)));
    pnp_power_ok = power_err_dis < power_tol;
else
    pnp_power_ok = false;
end
% 重连
t_rec = 8.0;
idx_rec = find(res_pnp.t_vec >= t_rec+2, 1);
if ~isempty(idx_rec)
    power_err_rec = max(abs(res_pnp.x2_mat(:, idx_rec:end) - mean(res_pnp.x2_mat(:, idx_rec:end),1)));
    pnp_power_rec_ok = power_err_rec < power_tol;
    freq_rec_ss = max(abs(res_pnp.x1_mat(:, idx_rec:end) - f_ref), [], 'all') < freq_tol;
else
    pnp_power_rec_ok = false;
    freq_rec_ss = false;
end

% 临界延迟裕度验证
margin_valid = (tau_max_sys > 5e-3 && tau_max_sys < 8e-3) && stable_tau5 && ~stable_tau8;

%% 5. 将所有指标写入 results.json （手动构造字符串保证长Key）
% 准备 key-value 对
kv = { ...
    'frequency_restoration_steady_state_error_no_ctd', freq_ss_1; ...
    'active_power_sharing_steady_state_error_no_ctd', power_ss_1; ...
    'frequency_restoration_settling_time_no_ctd', settle_f_1; ...
    'active_power_sharing_settling_time_no_ctd', settle_p_1; ...
    'frequency_restoration_settling_time_after_load_change_no_ctd', settle_f_load; ...
    'active_power_redistribution_settling_time_after_load_change_no_ctd', settle_p_load; ...
    'system_stability_under_ctd_below_margin', stable_tau5; ...
    'frequency_restoration_steady_state_error_under_ctd_below_margin', freq_ss_5; ...
    'active_power_sharing_steady_state_error_under_ctd_below_margin', power_ss_5; ...
    'frequency_restoration_settling_time_increase_under_ctd_below_margin', settle_f_5 - settle_f_1; ...
    'active_power_sharing_settling_time_increase_under_ctd_below_margin', settle_p_5 - settle_p_1; ...
    'system_instability_under_ctd_exceeding_margin', ~stable_tau8; ...
    'frequency_oscillation_under_ctd_exceeding_margin', freq_osc; ...
    'active_power_oscillation_under_ctd_exceeding_margin', power_osc; ...
    'plug_and_play_active_power_redistribution_on_dg_disconnection', pnp_power_ok; ...
    'plug_and_play_frequency_deviation_on_dg_disconnection', freq_dev; ...
    'plug_and_play_active_power_redistribution_on_dg_reconnection', pnp_power_rec_ok; ...
    'plug_and_play_frequency_recovery_on_dg_reconnection', freq_rec_ss; ...
    'critical_delay_margin_validation', margin_valid ...
};

% 构造json字符串
json_str = '{';
for k = 1:size(kv,1)
    key = kv{k,1};
    val = kv{k,2};
    if islogical(val)
        val_str = lower(mat2str(val));  % 'true' or 'false'
    else
        val_str = num2str(val, '%.6g');  % 数字
    end
    json_str = sprintf('%s"%s":%s,\n', json_str, key, val_str);
end
json_str = json_str(1:end-2); % 去掉末尾逗号
json_str = sprintf('%s\n}', json_str);

% 写入文件
fid = fopen('results.json', 'w');
fwrite(fid, json_str);
fclose(fid);
fprintf('results.json 已生成\n');

%% 局部函数定义 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
function res = run_simulation(dt, t_end, N, A_orig, b_orig, m_f, m_P, f_ref, tau, x1_0, x2_0, t_activation, events)
    num_steps = round(t_end/dt) + 1;
    t_vec = (0:num_steps-1)*dt;
    x1_mat = zeros(N, num_steps);
    x2_mat = zeros(N, num_steps);
    
    % 初始状态
    x1 = x1_0(:);
    x2 = x2_0(:);
    x1_mat(:,1) = x1;
    x2_mat(:,2) = x2;
    
    % 连接状态与当前矩阵
    active = ones(N,1);
    A_cur = A_orig;
    b_cur = b_orig;
    
    % 延迟历史缓冲
    delay_steps = round(tau/dt);
    if delay_steps > 0
        x1_hist = repmat(x1_0(:), 1, delay_steps+1);
        x2_hist = repmat(x2_0(:), 1, delay_steps+1);
    else
        x1_hist = x1_0(:);
        x2_hist = x2_0(:);
    end
    hist_idx = 1;  % 当前写入位置（循环缓冲）
    
    % 事件处理
    event_idx = 1;
    num_events = length(events);
    
    for k = 1:num_steps-1
        t = t_vec(k);
        
        % 处理事件（在控制计算之前）
        while event_idx <= num_events && t >= events(event_idx).time - dt/2
            ev = events(event_idx);
            if strcmp(ev.type, 'load_step')
                x2 = x2 + ev.value;
            elseif strcmp(ev.type, 'dg_disconnect')
                node = ev.node;
                if active(node)
                    Pd = x2(node);
                    active_nodes = find(active);
                    other_nodes = active_nodes(active_nodes ~= node);
                    if ~isempty(other_nodes)
                        x2(other_nodes) = x2(other_nodes) + Pd / length(other_nodes);
                    end
                    x2(node) = 0;
                    active(node) = 0;
                    A_cur(node, :) = 0;
                    A_cur(:, node) = 0;
                    b_cur(node) = 0;
                end
            elseif strcmp(ev.type, 'dg_reconnect')
                node = ev.node;
                if ~active(node)
                    active(node) = 1;
                    A_cur(node, :) = A_orig(node, :);
                    A_cur(:, node) = A_orig(:, node);
                    b_cur(node) = b_orig(node);
                    % 重新启动时，给其分配平均功率
                    active_nodes = find(active);
                    total_power = sum(x2(active_nodes));
                    avg_power = total_power / length(active_nodes);
                    x2(active_nodes) = avg_power;
                end
            end
            event_idx = event_idx + 1;
        end
        
        % 获取延迟状态
        if delay_steps > 0
            idx_del = k - delay_steps;
            if idx_del > 0
                x1_del = x1_mat(:, idx_del);
                x2_del = x2_mat(:, idx_del);
            else
                x1_del = x1_0(:);
                x2_del = x2_0(:);
            end
        else
            x1_del = x1;
            x2_del = x2;
        end
        
        % 计算控制输入
        u_f = zeros(N,1);
        u_P = zeros(N,1);
        if t >= t_activation
            for i = 1:N
                if active(i)
                    % 频率控制
                    u_f(i) = m_f * ( sum(A_cur(i,:) .* (x1_del' - x1_del(i))) + b_cur(i)*(f_ref - x1_del(i)) );
                    % 有功功率控制
                    u_P(i) = m_P * sum(A_cur(i,:) .* (x2_del' - x2_del(i)));
                end
            end
        end
        
        % 欧拉更新
        x1 = x1 + dt * u_f;
        x2 = x2 + dt * u_P;
        
        % 存储
        x1_mat(:, k+1) = x1;
        x2_mat(:, k+1) = x2;
    end
    
    res.t_vec = t_vec;
    res.x1_mat = x1_mat;
    res.x2_mat = x2_mat;
end

function T = find_settling_time(err_mat, t_vec, t0, tol)
    % err_mat: 误差信号 (N x num_steps), 每列对应一个时刻
    % 寻找从 t0 开始，所有节点误差均保持在 tol 内的时刻
    idx0 = find(t_vec >= t0, 1);
    if isempty(idx0), idx0 = 1; end
    max_err = max(abs(err_mat), [], 1);  % 各时刻最大节点误差
    inside = max_err <= tol;
    % 从 idx0 开始，找连续为真的起始点
    for k = idx0:length(inside)
        if all(inside(k:end))
            T = t_vec(k) - t0;
            return;
        end
    end
    T = NaN;  % 未进入容差带
end