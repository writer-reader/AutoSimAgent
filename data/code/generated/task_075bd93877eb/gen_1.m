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
B = diag(b_vec);

% 拉普拉斯矩阵与 M = L + B
D = diag(sum(A,2));
L = D - A;
M_mat = L + B;

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

% 初始状态：频率二次修正 x1 = f_i^n，有功标度 x2 = k_i^P P_i
x1_0 = f_ref * ones(N,1);        % f_i^n 初值 = 50 Hz
x2_0 = [0.5; 0.45; 0.4; 0.35; 0.5];  % 初始有功不平衡

% 仿真函数定义见末尾

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

%% 4. 指标计算

% ----- 辅助函数句柄 -----
calc_ss_error_f = @(res) max(abs(res.f_hist(:,end-round(1/dt):end) - f_ref), [], 2);
calc_ss_error_P = @(res) max(abs(res.x2_hist(:,end-round(1/dt):end) - ...
    mean(res.x2_hist(:,end-round(1/dt):end), 2)), [], 1);

% 调节时间：误差进入并保持在容差带内的时刻（相对参考时间）
function T_settle = calc_settling_time(t, error_signal, tol, t_ref)
    % error_signal: 1维误差信号（可以是平均绝对频率误差或最大有功偏差）
    idx_ref = find(t >= t_ref, 1, 'first');
    if isempty(idx_ref), idx_ref = 1; end
    err_abs = abs(error_signal(idx_ref:end));
    t_seg = t(idx_ref:end);
    in_band = err_abs <= tol;
    % 从后向前找第一个超出容差的索引
    idx_last_out = find(~in_band, 1, 'last');
    if isempty(idx_last_out)
        T_settle = 0;  % 始终在容差内
    else
        if idx_last_out == length(in_band)
            T_settle = inf;  % 最后仍超出，未稳定
        else
            T_settle = t_seg(idx_last_out+1) - t_ref;
        end
    end
end

% 频率平均绝对误差
avg_f_err = @(res) mean(abs(res.f_hist - f_ref), 1);
% 有功最大偏差
max_P_dev = @(res) max(abs(res.x2_hist - mean(res.x2_hist,1)), [], 1);

% --- 无延迟基本 ---
f_ss_error_0 = max(calc_ss_error_f(res_no_ctd));
P_ss_error_0 = max(calc_ss_error_P(res_no_ctd));

settle_f_0 = calc_settling_time(res_no_ctd.t, avg_f_err(res_no_ctd), freq_tol, t_activation);
settle_P_0 = calc_settling_time(res_no_ctd.t, max_P_dev(res_no_ctd), power_tol, t_activation);

% --- 无延迟负载变化 ---
% 负载变化后的恢复时间（从 t=6s 开始）
settle_f_load = calc_settling_time(res_load_change.t, avg_f_err(res_load_change), freq_tol, 6.0);
settle_P_load = calc_settling_time(res_load_change.t, max_P_dev(res_load_change), power_tol, 6.0);

% --- 延迟 5 ms ---
f_ss_error_5 = max(calc_ss_error_f(res_tau5));
P_ss_error_5 = max(calc_ss_error_P(res_tau5));

settle_f_5 = calc_settling_time(res_tau5.t, avg_f_err(res_tau5), freq_tol, t_activation);
settle_P_5 = calc_settling_time(res_tau5.t, max_P_dev(res_tau5), power_tol, t_activation);

% 稳定判定（基于最后 2s 的频率误差范围）
idx_stable = find(res_tau5.t >= res_tau5.t(end)-2, 1);
f_last = res_tau5.f_hist(:, idx_stable:end);
is_stable_5 = max(max(abs(f_last - f_ref))) < 0.5;  % 阀值

% 增加时间
increase_f = settle_f_5 - settle_f_0;
increase_P = settle_P_5 - settle_P_0;

% --- 延迟 8 ms ---
idx_stable8 = find(res_tau8.t >= res_tau8.t(end)-2, 1);
f_last8 = res_tau8.f_hist(:, idx_stable8:end);
is_stable_8 = max(max(abs(f_last8 - f_ref))) < 0.5;  % 应为 false
% 为判定是否恶化，可比较前期振荡
f_osc_amp_8 = max(max(abs(f_last8 - f_ref))) - min(min(abs(f_last8 - f_ref))); % 峰峰值
P_osc_amp_8 = max(max(abs(res_tau8.x2_hist(:,idx_stable8:end) - ...
    mean(res_tau8.x2_hist(:,idx_stable8:end),1))));

% --- 即插即用场景 ---
% DG5 断开后，有功重新分配指标：断开后新稳态的有功误差（最后1秒）
idx_pnp_end = round(1/dt);
P_after_disconnect = calc_ss_error_P(res_pnp); % 最后时刻有功偏差
% 频率偏差：DG5断开后，频率误差最大值
t_disconn = 6.0; t_reconn = 8.0;
idx_after_dis = find(res_pnp.t >= t_disconn, 1);
f_deviation_dis = max(abs(res_pnp.f_hist(:,idx_after_dis:end) - f_ref), [], 'all');

% 重连后，有功重新分配和频率恢复
P_after_reconn = calc_ss_error_P(res_pnp);  % 最终稳态有功误差（应恢复）
f_deviation_reconn = max(abs(res_pnp.f_hist(:,end-round(1/dt):end) - f_ref), [], 'all');

% --- 临界延迟验证 ---
% 理论值 tau_max_sys 应能正确预测：tau=5ms 稳定，tau=8ms 不稳定
margin_valid = (is_stable_5 == true) && (is_stable_8 == false);

%% 5. 汇总结果并输出 JSON
results = struct();
results.frequency_restoration_steady_state_error_no_ctd = f_ss_error_0;
results.active_power_sharing_steady_state_error_no_ctd = P_ss_error_0;
results.frequency_restoration_settling_time_no_ctd = settle_f_0;
results.active_power_sharing_settling_time_no_ctd = settle_P_0;
results.frequency_restoration_settling_time_after_load_change_no_ctd = settle_f_load;
results.active_power_redistribution_settling_time_after_load_change_no_ctd = settle_P_load;

results.system_stability_under_ctd_below_margin = is_stable_5;
results.frequency_restoration_steady_state_error_under_ctd_below_margin = f_ss_error_5;
results.active_power_sharing_steady_state_error_under_ctd_below_margin = P_ss_error_5;
results.frequency_restoration_settling_time_increase_under_ctd_below_margin = increase_f;
results.active_power_sharing_settling_time_increase_under_ctd_below_margin = increase_P;

results.system_instability_under_ctd_exceeding_margin = ~is_stable_8;
results.frequency_oscillation_under_ctd_exceeding_margin = f_osc_amp_8;
results.active_power_oscillation_under_ctd_exceeding_margin = P_osc_amp_8;

results.plug_and_play_active_power_redistribution_on_dg_disconnection = max(P_after_disconnect);
results.plug_and_play_frequency_deviation_on_dg_disconnection = f_deviation_dis;
results.plug_and_play_active_power_redistribution_on_dg_reconnection = max(P_after_reconn);
results.plug_and_play_frequency_recovery_on_dg_reconnection = f_deviation_reconn;

results.critical_delay_margin_validation = margin_valid;

% 写入 JSON
fid = fopen(fullfile(pwd, 'results.json'), 'w');
fwrite(fid, jsonencode(results));
fclose(fid);
fprintf('results.json 已生成。\n');

%% 6. 绘图保存（可选）
figure(1);
plot(res_no_ctd.t, res_no_ctd.f_hist'); grid on;
title('频率响应 (无延迟)'); xlabel('t/s'); ylabel('f/Hz');
exportgraphics(gcf, fullfile(pwd, 'fig_1.png'), 'Resolution', 200);

figure(2);
plot(res_no_ctd.t, res_no_ctd.x2_hist'); grid on;
title('有功共享 kP (无延迟)'); xlabel('t/s'); ylabel('k_i^P P_i');
exportgraphics(gcf, fullfile(pwd, 'fig_2.png'), 'Resolution', 200);

%% ================ 局部函数 ==================
function res = run_simulation(dt, t_end, N, A_base, b_base, m_f, m_P, f_ref, tau, ...
    x1_0, x2_0, t_activation, events)
    % 通用仿真器，支持事件（负载阶跃、DG通断）与通信延迟
    steps = round(t_end/dt);
    t = (0:steps-1)' * dt;

    % 初始化状态
    x1 = x1_0;   % f_i^n
    x2 = x2_0;   % k_i^P P_i
    f_hist = zeros(N, steps);
    x1_hist = zeros(N, steps);
    x2_hist = zeros(N, steps);

    % 当前邻接矩阵和牵制向量（可被事件修改）
    A = A_base;
    b_vec = b_base;
    B = diag(b_vec);
    L = diag(sum(A,2)) - A;
    M = L + B;

    % 延迟缓冲：若 tau > 0，记录历史状态
    if tau > 0
        tau_steps = round(tau/dt);
        f_buffer = repmat(f_ref * ones(N,1), 1, tau_steps);  % 初始填充为参考值
        x2_buffer = repmat(x2_0, 1, tau_steps);
    end

    % 事件处理辅助
    active_nodes = true(N,1);  % 所有节点激活
    event_idx = 1;
    num_events = length(events);

    for k = 1:steps
        tk = t(k);

        % ---- 事件检测与执行 ----
        while event_idx <= num_events && events(event_idx).time <= tk
            e = events(event_idx);
            switch e.type
                case 'load_step'
                    x2 = x2 + e.value;
                case 'dg_disconnect'
                    node = e.node;
                    active_nodes(node) = false;
                    x2(node) = 0;  % 输出功率降为0
                    % 移除该节点的通信连接
                    A(node, :) = 0;
                    A(:, node) = 0;
                    b_vec(node) = 0;
                    % 更新矩阵
                    L = diag(sum(A,2)) - A;
                    B = diag(b_vec);
                    M = L + B;
                    % 清空延迟缓冲对应节点状态为0，防止使用旧值
                    if tau > 0
                        f_buffer(node,:) = f_ref; % 设为参考
                        x2_buffer(node,:) = 0;
                    end
                case 'dg_reconnect'
                    node = e.node;
                    active_nodes(node) = true;
                    % 恢复原始连接
                    A = A_base;
                    b_vec = b_base;
                    L = diag(sum(A,2)) - A;
                    B = diag(b_vec);
                    M = L + B;
                    % 重连时节点状态保持不变（当前 x2(node) 可以是非零）
                    if tau > 0
                        f_buffer(node,:) = f_ref;
                        x2_buffer(node,:) = x2(node);
                    end
            end
            event_idx = event_idx + 1;
        end

        % 计算实际频率 f = x1 - x2
        f = x1 - x2;

        % 记录数据
        f_hist(:,k) = f;
        x1_hist(:,k) = x1;
        x2_hist(:,k) = x2;

        % 仅在激活后更新状态（或对于即插即用事件，始终更新？为统一，激活后才应用控制）
        if tk >= t_activation
            % 获取延迟状态
            if tau > 0
                f_delayed = f_buffer(:,1);
                x2_delayed = x2_buffer(:,1);
            else
                f_delayed = f;
                x2_delayed = x2;
            end

            % 频率控制律 (7): u_i^f = m_f * ( sum_j a_ij (f_j - f_i) + b_i (f_ref - f_i) )
            u_f = m_f * ( A * f_delayed - diag(sum(A,2)) * f_delayed + b_vec * (f_ref - f_delayed) );
            % 上式中 A*f - diag(sum(A,2)) * f 就是 -L * f，但为了使公式清晰，使用矩阵
            % 有功控制律 (11): u_i^P = m_P * sum_j a_ij (x2_j - x2_i)
            u_P = m_P * ( A * x2_delayed - diag(sum(A,2)) * x2_delayed );

            % 离散积分（欧拉）
            x1 = x1 + dt * u_f;
            x2 = x2 + dt * u_P;
        end

        % 更新延迟缓冲
        if tau > 0
            f_buffer = [f_buffer(:,2:end), f];
            x2_buffer = [x2_buffer(:,2:end), x2];
        end
    end

    % 构造输出结构
    res.t = t;
    res.f_hist = f_hist;
    res.x1_hist = x1_hist;
    res.x2_hist = x2_hist;
end

% 调节时间计算函数（放在独立文件或内嵌，这里定义为脚本末尾的局部函数）
function T_settle = calc_settling_time(t, error_signal, tol, t_ref)
    idx_ref = find(t >= t_ref, 1, 'first');
    if isempty(idx_ref), idx_ref = 1; end
    err_abs = abs(error_signal(idx_ref:end));
    t_seg = t(idx_ref:end);
    in_band = err_abs <= tol;
    idx_last_out = find(~in_band, 1, 'last');
    if isempty(idx_last_out)
        T_settle = 0;
    else
        if idx_last_out == length(in_band)
            T_settle = inf;
        else
            T_settle = t_seg(idx_last_out+1) - t_ref;
        end
    end
end