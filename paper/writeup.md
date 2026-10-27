# Read the function

### A token budget changes what repository search should return

Artem Tsygantsov

## Abstract

A local coding agent does not read a repository. It reads until a budget runs out. On the 280 SWE-bench Lite tasks whose fix lands inside a function, BM25 places the right file in its top 10 on 155 tasks, and the first 1024 tokens of those files contain the edited function 21 times. Packing whole function spans from BM25 over the function text contains it 89 times. Doing what an agent usually does, opening the top five files and only then taking functions, lands in between, at 68. On the 203 issues that never name the edited function, a walk from a similarly named test along the call graph votes 161 times and does not place that function in the top 10 once. The same order holds on the 115 function-level tasks in the competition's public development set: 39, 33 and 11.

## 1. What is measured

SWE-bench gives a model an issue and a checkout and keeps a patch only when the tests pass (Jimenez et al., 2024). The agents built on top of it spend much of their work finding the edit before they write it (Yang et al., 2024; Xia et al., 2024; Zhang et al., 2024; Ouyang et al., 2025). The Gemma 4 paper track asks for a result that still holds for a model on one machine, and past the competition's four development repositories (Markowitz et al., 2026). Notes on that development set already say the supplied embeddings barely separate symbols, and that a call-graph walk does not repair a missed seed (GraphLoc-129). They score a ranked list. This note scores whether the edited function fits in a fixed number of tokens.

The tasks are the public test split of SWE-bench Lite: 300 issues, twelve Python repositories. 280 fixes fall inside a function. Eighteen are module-level. One base commit was absent from the clone, and one file overflowed the parser. The ranker sees the problem statement only. Hints and the tests added for grading are not used. Gold is the smallest function or method, at the base commit, that contains a deleted line of the reference patch. A pure insertion is charged to the function around the insertion point. Test paths are ignored. A task is hidden when no gold function's name appears in the issue, ignoring generic verbs such as `get` and `update`. That split has 203 tasks. The other 77 name the function.

The same measurement was repeated on the competition's public development tasks, 129 pull requests in fastapi, rich, requests and httpx. The text is the pull request plus the issue it says it fixes. The diff is that pull request. 115 of the 129 edits fall inside a function.

Hit@10 is a gold function in the top ten, or a gold file for the file ranker. A budget hit means the whole function is inside the packed context. Every row uses `len(text) // 4` as its token count. Trees come from `git cat-file`. No model is called.

## 2. Three ways to spend the budget

All three use binary BM25: a query token counts once per document (Robertson and Zaragoza, 2009). Issue text is cut at 20,000 characters.

**File.** Rank files, drop tests, read each chosen file from the top until the budget ends. A function counts only when its last line is inside that prefix.

**Function.** Rank functions by BM25 over the path, the signature, the docstring and the body. Pack whole spans in that order. Skip a span that does not fit, and do not charge a span that overlaps one already taken.

**Shortlist.** Keep that same function order, drop every function whose file is outside the top one, three or five files, then pack spans. This is an agent opening a few files and only searching inside them.

`python -m editslice` does the function row. It is the one that wins the budget.

A symbol graph is included as a control, not as the method. The parser records spans, string constants, raised names, and calls that can be resolved statically: an import, `self`, a class attribute, a short re-export, or a name that exists once in the tree. Four channels stay silent when a signal hits more than eight functions. They are the function's name, a quoted string, a raised exception, and a test that shares a rare token with the issue, followed along those calls. Surviving lists are fused with reciprocal rank fusion at k = 60, with no fitted weights and no fallback to BM25. The implementation is `editslice/`.

## 3. Results

| | hit@10 | 1024 tokens | 4096 tokens |
| --- | ---: | ---: | ---: |
| file, read from the top | 155 | 21 | 66 |
| top file, then its functions | 54 | 48 | 58 |
| top five files, then their functions | 91 | 68 | 103 |
| function spans | 124 | 89 | 144 |
| fused graph channels | 52 | 36 | 63 |

Counts are out of 280. Hit@10 in the file row is a gold file. Every other hit@10 is a gold function. The token columns count a gold function whose source fits, and they can be compared across rows.

The file list is a bad thing to read. It names the right file 62 times at rank 1, and on 41 of those 62 the first 1024 tokens still miss the function. Packing functions from inside that one file moves the count from 21 to 48. Five files move it to 68. Throwing the file list away and packing the function ranking moves it to 89. The shortlist is not a refinement of the function ranking. It deletes edits whose file came sixth or worse, and many of those edits still fit in the function ranking's budget. At 4096 tokens the order is the same: 66 for the file prefix, 103 for five files, 144 for function spans.

On the 203 hidden issues the function spans contain the edit 47 times at 1024 tokens. The five-file shortlist contains it 37 times, the file prefix 14. The test bridge votes on 161 of the 203 and is never in the top 10. A quoted string is in the top 10 on 16. The fused channels are on 17. Nothing in the static graph beat the function text.

Django contributes 102 of the 280 tasks, SymPy 72. In Django the 1024-token counts are 43 for function spans, 25 for five files, 15 for the file prefix. In SymPy they are 18, 15 and 1. The smaller repositories are in `results/summary.json`.

On the development set the order is the same. Out of 115:

| | hit@10 | 1024 tokens | 4096 tokens |
| --- | ---: | ---: | ---: |
| file, read from the top | 69 | 11 | 32 |
| top five files, then their functions | 45 | 33 | 48 |
| function spans | 61 | 39 | 72 |

Where the issue names the function, 26 tasks, packing that name contains the edit 23 times at 1024 tokens. Function spans contain it 11 times there, and the file prefix contains it never. On the other 89, function spans contain it 28 times and the name channel 8. The rows are in `results/gemma4/`.

## 4. Where this sits

Retrieval localization has ranked files from bug reports for a long time (Zhou, Zhang and Lo, 2012). Agentless asks a model to go from file to element to line (Xia et al., 2024). Part of that step is available before any model runs: return the span, not the file. RepoGraph and GraphLocator use a graph as something a model can navigate or grow (Ouyang et al., 2025; Liu et al., 2026). That can still help after the span is known. On this split it does not find the span.

## 5. Limits

Gemma was not run, so a function in context is not a passing patch. Calls through local variables are unresolved, and that is part of the bridge result. Module-level edits are outside the table. A pure insertion can be charged to a neighbor. The development tasks are the public pull requests, not the hidden test and not a byte copy of the competition file. Both sets are Python. Another tokenizer would move the counts. It would move every row by the same rule, and the claim is the order.

## References

Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., and Narasimhan, K. SWE-bench: Can language models resolve real-world GitHub issues? ICLR, 2024.

Yang, J., Jimenez, C. E., Wettig, A., Lieret, K., Yao, S., Narasimhan, K., and Press, O. SWE-agent: Agent-computer interfaces enable automated software engineering. NeurIPS, 2024.

Xia, C. S., Deng, Y., Dunn, S., and Zhang, L. Agentless: Demystifying LLM-based software engineering agents. arXiv:2407.01489, 2024.

Zhang, Y., Ruan, H., Fan, Z., and Roychoudhury, A. AutoCodeRover: Autonomous program improvement. ISSTA, 2024.

Ouyang, S., Yu, W., Ma, K., Xiao, Z., Zhang, Z., Jia, M., Han, J., Zhang, H., and Yu, D. RepoGraph: Enhancing AI software engineering with repository-level code graph. ICLR, 2025.

Zhou, J., Zhang, H., and Lo, D. Where should the bugs be fixed? ICSE, 2012.

Robertson, S. and Zaragoza, H. The probabilistic relevance framework: BM25 and beyond. Foundations and Trends in Information Retrieval, 3(4):333–389, 2009.

Liu, W., Peng, C., Gao, P., Liu, A., Zhang, W., Zhao, H., and Jin, Z. GraphLocator: Graph-guided causal reasoning for issue localization. arXiv:2512.22469, 2026.

Markowitz, E., Perozzi, B., Rózemberczki, B., Cameron, G., Hemmati, H., Li, Y., Galkin, M., Farhadi, M., Holbrook, R., and Oldacre, A. Google - The Gemma 4 Developer Agent Paper Track. Kaggle, 2026.

GraphLoc-129: SWE bug localization benchmark. Kaggle dataset, 2026.
