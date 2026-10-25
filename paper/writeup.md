# What fits in the budget

### Function spans, file retrieval, and the signals that do not find the edit

Artem Tsygantsov

## Abstract

A coding agent that has to work on a laptop does not usually fail first at writing the patch. It fails at deciding which lines are worth the context it has left. The Gemma 4 developer-agent setting makes the constraint concrete: a fixed open model, a repository snapshot, a symbol graph, and a context that cannot hold the repository. Public measurements on the competition's development set already found that the supplied embeddings barely separate symbols, and that walking the call graph does not repair a bad seed. This note asks the question those measurements leave open. Once the agent can only read a few thousand tokens, does a file ranking still contain the edit, and does the graph find the function when the issue never names it?

The graph is built with the Python parser. Four channels vote, and each stays silent when its signal hits more than eight functions: the function's name, a quoted string, an exception the function raises, and a test whose name shares a rare token with the issue and whose resolved calls land in production code. Reciprocal rank fusion mixes whatever lists survive. The unit that gets packed into the budget is the function span, not the prefix of a file. The baselines are binary BM25 over those same functions, and binary BM25 over files.

On SWE-bench Lite the file ranker looks fine at hit@10 and then fails the budget: the right file is often on the short list, and the first 1024 tokens of it usually do not contain the edit. Packing function spans from the same lexical score contains the edit several times as often. The test bridge votes on most issues that never name the function and does not rank that function in the top 10 once. A rare quoted string is the only channel with any precision, and fusion does not catch function-level BM25.

## 1. Introduction

Repository-level bug fixing, as SWE-bench set it up, gives a model an issue and a checkout and accepts a patch only when the project's tests pass (Jimenez et al., 2024). The systems that do this well spend a large part of their machinery on finding the file and the function before they edit anything. SWE-agent put the search inside a loop over a terminal (Yang et al., 2024). Agentless took the loop out and asked a model for a file, then an element, then a line (Xia et al., 2024). AutoCodeRover and RepoGraph both bet that a structural index, an AST search or a repository graph, would make the search less of a crawl (Zhang et al., 2024; Ouyang et al., 2025).

The Gemma 4 paper track asks for a measurement that still matters off that leaderboard, and past the four development repositories (Markowitz et al., 2026). Two public analyses of those repositories already report that the supplied 256-dimensional embeddings barely separate symbols, and that walking the call graph does not bring back a symbol the lexical list missed (GraphLoc-129). Both analyses score a ranked list. An agent does not submit a ranked list. It reads, and a file at rank 1 has not been found if the budget runs out before the edited function. This paper measures localization as packing. The function either fits or it does not.

The second question is the one the negative graph results leave open. If the issue never uses the function's name, is there a signal in the graph that lexical overlap on the function text does not already capture? We tried the three a static reader can compute without a model: a string the issue quotes, an exception the function raises, and the production function reached from a test whose name tracks the issue. Each one abstains when it would otherwise point everywhere. A channel that returns half the repository is not evidence, and letting it vote buries the channels that were specific.

## 2. Method

A file is parsed with the standard library. Functions, methods and classes become nodes. A node keeps its span, its signature, its docstring, the string constants in its own body, and the exceptions it raises. Nested definitions keep their own constants and their own raises. Call edges are only the ones a static reader can defend: a name imported into the file, a module-level function in the same file, `self` or `cls` resolved to the enclosing class, an attribute of a class that was imported, a re-export followed through at most four hops, or a name that exists in exactly one place in the tree. A call through a local variable stays unresolved. That miss is common, and the bridge result below should be read with it in mind. Test files stay in the graph, because the bridge needs them, and they are excluded from the list of functions the agent is invited to edit.

An issue is reduced to identifiers, tokens and quoted strings. A name counts as an exception when it ends in `Error`, `Exception` or `Warning`, or when it is CamelCase of at least six characters. The second rule is there because projects invent names like `PortInUse`. Ordinary capitalized words get into that set too. They only matter if some function actually raises them, and the fanout rule drops them when that happens all over the repository.

Four channels then rank production functions.

The name channel scores an exact function name when the issue contains it, the name is at least five characters, it is not a generic verb (`get`, `run`, `update`, and a short list of the same kind), and no more than eight functions share it. A token from the name adds a point when it is at least five characters long and occurs in at most eight function names. If more than twenty functions score, only the exact-name hits are kept, and if those are still too many the channel returns nothing.

The literal channel keeps a quoted string of at least eight characters. It matches a function whose body contains that string, by equality, or by containment when the shorter side has at least twelve characters. A string that sits in more than eight functions is treated as boilerplate and dropped. The raise channel is the same intersection for exception names, with the same cap.

The bridge starts from test functions. A test is a seed when its name shares a token of length at least five with the issue and that token belongs to at most eight tests. At most eight tests seed the walk. We take their resolved production callees. If that set contains between one and twenty functions, we also add the functions those callees call, but only while the union stays inside twenty. If the tests resolved only into other tests, we walk one hop further. Anything wider, and the channel abstains.

The lists that come back are fused with reciprocal rank fusion at k = 60, unweighted. There is no learned mixture. If every channel abstains, the fused list is empty and the method records a miss. It does not fall back to BM25. The baseline is allowed to win, and the comparison is only honest if a fallback is not smuggled into the method.

Packing walks a ranked list and charges each function its whole span, at one token per four characters, the same estimate for every method. A span that does not fit is skipped. A span that overlaps one already taken is not charged again. The file baseline is binary BM25 over the file text, with test files removed. Each selected file is then read from the top until the budget runs out, and a function counts as present only when its last line sits inside that prefix. Function BM25 is the same ranker over the function's path, signature, docstring and body, and it is packed as spans. Binary means a repeated token counts once per document. Issue text is cut at 20,000 characters and a file's tokens at 4,000, so a pasted log cannot win by repetition.

The fanout cap is 8 in the numbers below. The run also records 4 and 16. Eight was chosen because it is a list a person can look at, not because it maximized a score.

`python -m editslice` prints the spans that fit, with file, lines and which channels voted. The evaluation never calls a model. It checks whether the gold function is among those spans.

## 3. Setup

The tasks are the public test split of SWE-bench Lite, 300 issues across twelve Python repositories. It is used here instead of the competition's 129 development tasks for two reasons. It can be fetched without a Kaggle credential, and it is not the four repositories the competition graph was built on, so a result is less likely to be a quirk of FastAPI and Rich. The text the ranker sees is the problem statement alone. Maintainer hints are not used. The test patch SWE-bench adds for grading is not used. Gold is the smallest function or method, in the tree at the base commit, that contains a deleted line of the reference patch. A pure insertion, which has no deleted line, is attributed to the function that contains the line it is inserted before. Edits that land outside any function, a module-level constant for example, are counted and then left out of the rates. Test paths in the patch are ignored.

A task is called name-visible when the issue contains a gold function's name as an identifier, under the same length and generic-verb rules as the name channel. The hidden split is everything else. That is the split where a graph signal would have to earn its place, because the name is not sitting in the issue waiting to be matched.

Hit@10 is a gold function in the top 10, or a gold file for the file ranker. A budget hit is the function's source fully inside the packed context. Both use `len(text) // 4` as the token estimate. The tree at `base_commit` is read with `git cat-file`, with nothing installed and no model called. Rows are in `results/per_task.jsonl`.

## 4. Results

Of the 300 tasks, 280 are edits inside a function and enter the table. Eighteen change only code that sits outside any function, one base commit was not in the clone, and one file defeated the parser with a recursion limit. Of the 280, 77 name a gold function in the issue and 203 do not.

Read the 1024-token column before hit@10. File BM25 places a gold file in its top 10 on 155 of 280 tasks, and in its top 1 on 62. On 41 of those 62, the first 1024 tokens of the file do not contain the edited function. Across all 280 tasks the file prefix contains the function 21 times. Function BM25, packing spans from the same family of score, contains it 89 times. That is the result. A metric that stops at file hit@10 will keep recommending file retrieval, and an agent with a tight budget will keep reading the wrong lines of the right file.

The four channels do not rescue the 203 issues that never name the function. The name channel has almost nothing to match there, which is what the split means: 3 hits in the top 10. The raise channel votes 18 times and is right once. The bridge votes 161 times, which means the abstention rule did not consider it vague, and it does not place the gold function in the top 10 once. The tests that share a token with the issue call a public wrapper, or they call a name we resolved to the wrong function, and the function the patch edits is one unresolved attribute lookup further down. Walking one extra hop, while the list stays under twenty, does not repair a missing edge.

The literal channel is the narrow exception. It votes on 69 of the hidden issues. On 16 of those the gold function is in its top 10, and on 7 it is first. In `matplotlib-24265` the report quotes `seaborn-colorblind`, the patch edits the function that contains that string, and function BM25 does not rank the function in its top 10. Cases of that shape exist. They are not common enough to carry the average: function BM25 still finds 70 of the 203 hidden edits in its top 10, against 16 for the literal channel and 17 for the fusion.

The fusion sits next to the name channel, not next to function BM25. On all 280 tasks it has 52 top-10 hits against 124 for function BM25, and 36 functions inside 1024 tokens against 89. Unweighted fusion gives the bridge's first guess the same weight as a name hit. The mixture was left unweighted on purpose. Fitting it on this split would only have hidden the bridge, and the bridge's failure is part of the result.

Fanout 4, 8 and 16 gives the fused list 18, 17 and 17 top-10 hits on the hidden split. The cap is not where the result comes from. The same ordering holds in the large repositories: Django is 102 scored tasks, function BM25 inside 1024 tokens on 43 of them and the file prefix on 15; SymPy is 72, 18 against 1. The repositories with fewer than ten tasks are too small to carry a separate claim. Per-repository counts are in `results/summary.json`.

| method | hit@10 | in 1024 tokens | in 4096 tokens |
| --- | ---: | ---: | ---: |
| file BM25 | 155 | 21 | 66 |
| function BM25 | 124 | 89 | 144 |
| fused channels | 52 | 36 | 63 |
| name only | 42 | 29 | 52 |
| quoted string | 23 | 15 | 22 |
| test bridge | 6 | 3 | 5 |
| raised exception | 2 | 2 | 2 |

Counts are out of 280. Hit@10 for the file row is a gold file in the top 10 files. Every other hit@10 is a gold function in the top 10 functions. The token columns are a gold function's source sitting fully inside the packed context, and they are comparable across rows.

On the 203 hidden issues the same table is 100, 14 and 39 for file BM25; 70, 47 and 84 for function BM25; 17, 10 and 19 for the fusion; 16, 8 and 15 for the quoted string; and 0, 0 and 0 for the bridge.

One concrete case for the literal channel is `matplotlib-24265`. The report says that `plt.style.library["seaborn-colorblind"]` raises a key error. The string is rare, the function that contains it is the one the patch edits, and function BM25 does not place that function in its top 10. Cases like this exist. There are not many of them, which is why the channel's average stays well below BM25.

## 5. Related work

BugLocator ranked files from the words in a bug report, and a long line of retrieval-based localization followed it (Zhou, Zhang and Lo, 2012). BM25 is the ranking function under a lot of that work and under both baselines here (Robertson and Zaragoza, 2009). The recent agent papers changed the interface more than they changed the evidence. Agentless is explicit that localization is a hierarchy, file then element then line, and it asks a model to walk the hierarchy. We stop one step earlier and ask how much of that hierarchy is just the unit you retrieve, with no model in the loop. If function-level lexical retrieval at a fixed budget beats file-level retrieval at the same budget, then part of what an Agentless-style pass is doing is repairing a unit error, and a cheaper ranker can do that repair before any model is called.

RepoGraph plugs a repository graph into an agent that already localizes and raises the resolve rate on SWE-bench (Ouyang et al., 2025). Their graph is a navigation aid for a model that can ask for neighbors. The graph here is asked to be a seed, and a navigation aid can be useful after a good seed while being useless as one. GraphLocator has a model grow a causal graph over a repository dependency structure (Liu et al., 2026). Those gains spend a model. The negative result here is what the graph gives you without one.

On the competition data, the public graph-retrieval benchmark and GraphLoc-129 both concluded that the provided embeddings do not separate nodes and that call-graph expansion does not repair a missed seed. The embeddings are not remeasured here. That conclusion is the reason the experiment was spent on seeds and on tokens, on a benchmark that is not the competition's development set.

## 6. What this does not show

Gemma was not run. A slice that contains the edited function is not, by itself, a higher fraction of passing tests. Localization is a necessary condition. It is not the whole task. The function can be in context and the patch can still be wrong.

The call resolver misses edges through local variables, so the bridge result is partly about that resolver. A heavier alias analysis might recover some hidden edits, or it might fan out until the channel abstains. Gold is the function around a deleted line. Module-level edits are outside the rates, and insertion-only hunks can be slightly generous. SWE-bench Lite is Python and it is not the competition's hidden set. The token estimate would move under Gemma's tokenizer. Every method uses the same one, and the claim is the ordering.

## References

Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., and Narasimhan, K. SWE-bench: Can language models resolve real-world GitHub issues? ICLR, 2024.

Yang, J., Jimenez, C. E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K., and Press, O. SWE-agent: Agent-computer interfaces enable automated software engineering. NeurIPS, 2024.

Xia, C. S., Deng, Y., Dunn, S., and Zhang, L. Agentless: Demystifying LLM-based software engineering agents. arXiv:2407.01489, 2024.

Zhang, Y., Ruan, H., Fan, Z., and Roychoudhury, A. AutoCodeRover: Autonomous program improvement. ISSTA, 2024.

Ouyang, S., Yu, W., Ma, K., Xiao, Z., Zhang, Z., Jia, M., Han, J., Zhang, H., and Yu, D. RepoGraph: Enhancing AI software engineering with repository-level code graph. ICLR, 2025.

Zhou, J., Zhang, H., and Lo, D. Where should the bugs be fixed? More accurate information retrieval based bug localization based on bug reports. ICSE, 2012.

Robertson, S. and Zaragoza, H. The probabilistic relevance framework: BM25 and beyond. Foundations and Trends in Information Retrieval, 3(4):333–389, 2009.

Liu, W., Peng, C., Gao, P., Liu, A., Zhang, W., Zhao, H., and Jin, Z. GraphLocator: Graph-guided causal reasoning for issue localization. arXiv:2512.22469, 2026.

Markowitz, E., Perozzi, B., Rózemberczki, B., Cameron, G., Hemmati, H., Li, Y., Galkin, M., Farhadi, M., Holbrook, R., and Oldacre, A. Google - The Gemma 4 Developer Agent Paper Track. Kaggle, 2026. https://www.kaggle.com/competitions/gemma-4-developer-agent-paper

GraphLoc-129: SWE bug localization benchmark. Kaggle dataset, 2026. https://www.kaggle.com/datasets/keykavus/graphloc-129

Gemma 4 graph-retrieval benchmark. Hugging Face dataset HIMANSHUKUMARJHA/gemma4-graph-retrieval-benchmark, 2026.
