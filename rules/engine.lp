% Semantics of RDDC processing rules, in Answer Set Programming (clingo 5).
%
% scripts/rules_engine.py exports a rule set (rules/rules.yaml) and deposits as facts;
% this program computes every state reachable from them and the violations.
% Without route.lp/plan.lp the program is stratified, so it has one answer set.
%
% A state is s(Class, Standard, Zone, Mask): Mask is a bit set of data properties,
% one bit per prop(P, Bit); Standard is a standard id or none. A profile holds the facts
% about a deposit that no workflow changes: its file set class, techniques, the batch
% interaction and the source register entry. States are computed per profile, so
% deposits with the same profile share them.
%
% Input facts
%   class(C). isa(C, A).                  every class C with each ancestor A (reflexive)
%   prop(P, Bit). mask(M).                data properties; every mask value
%   zone(Z). initial(Z). standard(S).
%   workflow(W). kind(W, K). reads(W, Z). writes(W, Z). produces(W, C).
%   produces_std(W, S). clears(W, P). sets(W, P). wprio(W, N). consumes(W, Cond).
%   cond(Cond). c_class(Cond, C). c_std(Cond, S). c_any(Cond, P). c_none(Cond, P).
%   c_fileset(Cond, F). c_tech(Cond, T). c_inter(Cond, I). c_fmt(Cond, MediaType).
%   c_src(Cond, Field). c_src_any(Cond, Field, V). c_src_none(Cond, Field, V).
%   target(T, Cond, Priority). goal_class(T, C). goal_std(T, S). goal_zone(T, Z).
%   goal_none(T, P).                     the goal state lacks property P
%   obligation(O, Cond, Kind). before_zone(O, Z). before_wf(O, W).
%   prohibition(H, Cond). prohibited(H, Z).
%   interaction_rule(I, W). covers(W, Z).
%   profile(P). p_fileset(P, F). p_tech(P, T). p_inter(P, I). p_fmt(P, MediaType).
%   p_src(P, Field, V).
%   start(P, C, S, M).                    a deposit: profile and starting state

% --- conditions: each part is checked on its own, so matching stays positive ---
has_class(K) :- c_class(K, _).
has_std(K) :- c_std(K, _).
has_any(K) :- c_any(K, _).
has_fileset(K) :- c_fileset(K, _).
has_tech(K) :- c_tech(K, _).
has_inter(K) :- c_inter(K, _).
has_fmt(K) :- c_fmt(K, _).

class_ok(K, C) :- cond(K), class(C), not has_class(K).
class_ok(K, C) :- c_class(K, A), isa(C, A).
std_ok(K, S) :- cond(K), std_or_none(S), not has_std(K).
std_ok(K, S) :- c_std(K, S).
std_or_none(S) :- standard(S).
std_or_none(none).

any_hit(K, M) :- c_any(K, P), prop(P, B), mask(M), M & B != 0.
none_hit(K, M) :- c_none(K, P), prop(P, B), mask(M), M & B != 0.
props_ok(K, M) :- cond(K), mask(M), not has_any(K), not none_hit(K, M).
props_ok(K, M) :- any_hit(K, M), not none_hit(K, M).

fileset_ok(K, P) :- cond(K), profile(P), not has_fileset(K).
fileset_ok(K, P) :- c_fileset(K, F), p_fileset(P, G), isa(G, F).
tech_ok(K, P) :- cond(K), profile(P), not has_tech(K).
tech_ok(K, P) :- c_tech(K, T), p_tech(P, T).
inter_ok(K, P) :- cond(K), profile(P), not has_inter(K).
inter_ok(K, P) :- c_inter(K, I), p_inter(P, I).
fmt_ok(K, P) :- cond(K), profile(P), not has_fmt(K).
fmt_ok(K, P) :- c_fmt(K, F), p_fmt(P, F).
% A register test: some value in anyOf (if given), and no value in noneOf.
src_hit(K, P, F) :- c_src_any(K, F, V), p_src(P, F, V).
src_bad(K, P) :- c_src_any(K, F, _), profile(P), not src_hit(K, P, F).
src_bad(K, P) :- c_src_none(K, F, V), p_src(P, F, V).
profile_ok(K, P) :- fileset_ok(K, P), tech_ok(K, P), inter_ok(K, P), fmt_ok(K, P), not src_bad(K, P).

% Matching is computed only where a rule needs it.
need(K, P, St) :- consumes(W, K), reads(W, Z), reach(P, St), St = s(_, _, Z, _).
need(K, P, St) :- target(_, K, _), st0(P, St).
need(K, P, St) :- obligation(_, K, _), reach(P, St).
need(K, P, St) :- prohibition(H, K), prohibited(H, Z), reach(P, St), St = s(_, _, Z, _).
match(K, P, s(C, S, Z, M)) :-
    need(K, P, s(C, S, Z, M)),
    class_ok(K, C), std_ok(K, S), props_ok(K, M), profile_ok(K, P).

% --- workflow effects ---
has_produces(W) :- produces(W, _).
has_produces_std(W) :- produces_std(W, _).
out_class(W, C, D) :- produces(W, D), class(C).
out_class(W, C, C) :- workflow(W), class(C), not has_produces(W).
out_std(W, S, T) :- produces_std(W, T), std_or_none(S).
out_std(W, S, S) :- workflow(W), std_or_none(S), not has_produces_std(W).
clear_mask(W, CM) :- workflow(W), CM = #sum { B, P : clears(W, P), prop(P, B) }.
set_mask(W, SM) :- workflow(W), SM = #sum { B, P : sets(W, P), prop(P, B) }.

% --- reachable states ---
st0(P, s(C, S, Z, M)) :- start(P, C, S, M), initial(Z).
reach(P, St) :- st0(P, St).
step(P, s(C, S, Z, M), W, s(C2, S2, Z2, M2)) :-
    reach(P, s(C, S, Z, M)), consumes(W, K), reads(W, Z),
    match(K, P, s(C, S, Z, M)),
    writes(W, Z2), out_class(W, C, C2), out_std(W, S, S2),
    clear_mask(W, CM), set_mask(W, SM), M2 = (M & (~CM)) ? SM.
reach(P, St) :- step(P, _, _, St).

% --- targets: the matching target with the lowest priority number ---
tmatch(P, St, T, N) :- st0(P, St), target(T, K, N), match(K, P, St).
beaten(P, St, N) :- tmatch(P, St, _, N), tmatch(P, St, _, N2), N2 < N.
chosen(P, St, T) :- tmatch(P, St, T, N), not beaten(P, St, N).
has_goal_class(T) :- goal_class(T, _).
has_goal_std(T) :- goal_std(T, _).
gclass_ok(T, C) :- target(T, _, _), class(C), not has_goal_class(T).
gclass_ok(T, C) :- goal_class(T, A), isa(C, A).
gstd_ok(T, S) :- target(T, _, _), std_or_none(S), not has_goal_std(T).
gstd_ok(T, S) :- goal_std(T, S).
% Goal states, only for targets some deposit of the profile has.
wanted(P, T) :- chosen(P, _, T).
gprops_bad(T, M) :- goal_none(T, Q), prop(Q, B), mask(M), M & B != 0.
goal(P, T, s(C, S, Z, M)) :-
    wanted(P, T), reach(P, s(C, S, Z, M)),
    goal_zone(T, Z), gclass_ok(T, C), gstd_ok(T, S), not gprops_bad(T, M).
% States from which a goal of target T can be reached (backwards from the goals).
to_goal(P, T, St) :- goal(P, T, St).
to_goal(P, T, St) :- step(P, St, _, St2), to_goal(P, T, St2).

% --- obligations: open(P, O, St) if some route reaches St with duty O open ---
% A duty is open in a state that matches its condition; otherwise it stays open after
% a step of any kind but the required one.
open(P, O, St) :- reach(P, St), obligation(O, K, _), match(K, P, St).
open(P, O, St2) :- open(P, O, St), step(P, St, W, St2), obligation(O, K, R),
    not match(K, P, St2), not kind(W, R).

% --- violations: reported, not forbidden, so every one is listed ---
% violation(Rule, Profile, State): State is where the rule is broken; for target
% rules it is the deposit's starting state.
violation(obligation(O), P, St) :- open(P, O, St), St = s(_, _, Z, _), before_zone(O, Z).
violation(obligation(O), P, St) :- open(P, O, St), step(P, St, W, _), before_wf(O, W).
violation(prohibition(H), P, St) :-
    reach(P, St), prohibition(H, K), match(K, P, St), St = s(_, _, Z, _), prohibited(H, Z).
violation(no_target, P, St) :- st0(P, St), not chosen(P, St, _).
violation(target_conflict(T1, T2), P, St) :- chosen(P, St, T1), chosen(P, St, T2), T1 < T2.
violation(no_route(T), P, St) :- chosen(P, St, T), not to_goal(P, T, St).

% A batch-level interaction must reach every zone that data can reach.
reached_zone(Z) :- reach(_, s(_, _, Z, _)).
iviolation(interaction(I), Z) :- interaction_rule(I, W), reached_zone(Z), not covers(W, Z).

% No cycles. A state is acyclic if every state it steps to is (least fixpoint, so a
% state on a cycle, or one that can step into a cycle, is not).
outdeg(P, A, N) :- reach(P, A), N = #count { B : step(P, A, _, B) }.
acyclic(P, A) :- outdeg(P, A, N), #count { B : step(P, A, _, B), acyclic(P, B) } >= N.
violation(cycle, P, A) :- reach(P, A), not acyclic(P, A).

% Warnings: workflows no deposit can run.
used(W) :- step(_, _, W, _).
unused(W) :- consumes(W, _), not used(W).

#show violation/3.
#show iviolation/2.
#show unused/1.
