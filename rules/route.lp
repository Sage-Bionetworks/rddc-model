% Routes for the files of one batch, on top of engine.lp.
%
% Input facts
%   file(X, Profile, C, S, M).   a data file and its starting state (also a start/4 fact)
%   go(X, T, W).                 workflow W runs on file X at step T (0, 1, ...)
%   observed(X, T, M).           after step T - 1, a workflow reported that file X has
%                                the properties in mask M (replacing the predicted ones)
%
% scripts/orchestrate.py gives the steps that ran as go/3 facts, to check them; with
% plan.lp, clingo chooses the steps still to run.

fprof(X, P) :- file(X, P, _, _, _).
at(X, s(C, S, Z, M), 0) :- file(X, _, C, S, M), initial(Z).
observed_at(X, T) :- observed(X, T, _).
at(X, St2, T + 1) :- at(X, St, T), go(X, T, W), fprof(X, P), step(P, St, W, St2),
    not observed_at(X, T + 1).
at(X, s(C, S, Z, M), T + 1) :- at(X, St, T), go(X, T, W), fprof(X, P),
    step(P, St, W, s(C, S, Z, _)), observed(X, T + 1, M).
% A reported state may be one the engine did not predict; explore from it too.
reach(P, St) :- at(X, St, _), fprof(X, P).

can_run(X, T, W) :- at(X, St, T), go(X, T, W), fprof(X, P), step(P, St, W, _).
route_end(X, T) :- at(X, _, T), not go(X, T, _).
ftarget(X, Tg) :- file(X, P, C, S, M), initial(Z), chosen(P, s(C, S, Z, M), Tg).
at_goal(X, T) :- at(X, St, T), fprof(X, P), ftarget(X, Tg), goal(P, Tg, St).

% Duties along the route, as in engine.lp but for this route only.
ropen(X, O, T) :- at(X, St, T), fprof(X, P), obligation(O, K, _), match(K, P, St).
ropen(X, O, T + 1) :- ropen(X, O, T), at(X, St, T + 1), go(X, T, W), fprof(X, P),
    obligation(O, K, R), not match(K, P, St), not kind(W, R).

% rviolation(Rule, File, Step)
rviolation(cannot_run(W), X, T) :- go(X, T, W), not can_run(X, T, W).
rviolation(obligation(O), X, T) :- ropen(X, O, T), at(X, s(_, _, Z, _), T), before_zone(O, Z).
rviolation(obligation(O), X, T) :- ropen(X, O, T), go(X, T, W), before_wf(O, W).
rviolation(prohibition(H), X, T) :-
    at(X, St, T), fprof(X, P), prohibition(H, K), match(K, P, St),
    St = s(_, _, Z, _), prohibited(H, Z).
rviolation(not_at_target, X, T) :- route_end(X, T), not at_goal(X, T).
% A workflow runs at most once on a file: nothing is retried automatically, so a
% finding (say, free text left after de-identification) waits for a person.
rviolation(repeated(W), X, T2) :- go(X, T1, W), go(X, T2, W), T1 < T2.

#show go/3.
#show rviolation/3.
#show ftarget/2.
