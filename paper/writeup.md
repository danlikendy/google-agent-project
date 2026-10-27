# The edit is a thousand tokens down

### A correct file retrieval still starts too early

Artem Tsygantsov

## Abstract

BM25 often names the right file, and the edit is still not in what an agent reads first. On 62 SWE-bench Lite tasks where the top-ranked file is the one that changes, the edited function begins a median of 1727 tokens into that file and is not finished until 2192. Reading the file from the top contains the function 21 times. Packing whole functions from inside the same file contains it 48 times. On the 28 development tasks with the same property the function begins at a median of 1629 tokens: the prefix contains it 9 times, the functions inside the file 17. Ranking functions across the whole repository stays ahead of both, because the top file is often the wrong file.

## 1. What is measured

SWE-bench gives a model an issue and a checkout and keeps a patch when the tests pass (Jimenez et al., 2024). Agents spend much of the work finding the edit before they write it (Yang et al., 2024; Xia et al., 2024; Zhang et al., 2024; Ouyang et al., 2025). Public notes on the Gemma 4 development set already score whether a file or a graph node is in a ranked list (GraphLoc-129; the graph-retrieval benchmark of Jha, 2026). A list is not a read. This note measures where the edited function sits inside the file that was ranked first, and whether a fixed token budget reaches it.

Two sets are used. SWE-bench Lite contributes 300 issues from twelve Python repositories; 280 fixes fall inside a function. The competition's public development tasks contribute 129 pull requests from fastapi, rich, requests and httpx; 115 fixes fall inside a function. The issue text for the second set is the pull request plus the issue it says it fixes. The ranker sees that text and the tree at the base commit. Gold is the smallest function or method that contains a deleted line of the reference diff. A pure insertion is charged to the function around the insertion point. Test paths are ignored.

Hit@10 is a gold function in the top ten, or a gold file for the file ranker. A budget hit means the whole function is inside the packed context. Every count uses `len(text) // 4`. For a task whose top file is a gold file, the position of the edit is the token cost of that file through the end line of its earliest gold function, and the cost of the lines before the function starts. Trees come from `git cat-file`. No model is called.

## 2. Two ways to read a file that is already known

Both ways use binary BM25: a query token counts once per document (Robertson and Zaragoza, 2009). Issue text is cut at 20,000 characters.

**From the top.** Rank files, drop tests, read each file from the first line until the budget ends. A function counts only when its last line is inside that prefix.

**Functions inside the file.** Rank functions by BM25 over the path, the signature, the docstring and the body. Keep only the functions that live in the top file, or in the top five, and pack whole spans. Skip a span that does not fit.

**Functions, no file list.** The same function ranking, with no file filter. `python -m editslice` does this. It is the best list when the top file is allowed to be wrong. The measurement below is about the other case, when the top file is right and the only question is where to start reading.

## 3. Results

On SWE-bench Lite the top file is right 62 times out of 280. The edited function in that file starts at a median of 1727 tokens and ends at a median of 2192. On 36 of the 62 it has not started by token 1024. On 5 more it has started and not ended. The prefix therefore contains the function 21 times, and misses it 41 times. Packing the functions that BM25 ranks inside that same file contains it 48 times. Three of the functions that remain missing are themselves larger than 1024 tokens.

On the development set the top file is right 28 times out of 115. The function starts at a median of 1629 tokens and ends at a median of 2137. It has not started by token 1024 on 17 of the 28, and has not ended on 19. The prefix contains it 9 times. The functions inside the file contain it 17 times.

The file list is still the wrong place to stop. Once tasks whose top file is wrong are put back in, ranking functions over the whole tree contains the edit more often than ranking them inside the top file.

| | hit@10 | 1024 tokens | 4096 tokens |
| --- | ---: | ---: | ---: |
| SWE-bench Lite, file from the top | 155 | 21 | 66 |
| SWE-bench Lite, functions in the top file | 54 | 48 | 58 |
| SWE-bench Lite, functions in the top five files | 91 | 68 | 103 |
| SWE-bench Lite, functions, no file list | 124 | 89 | 144 |
| development set, file from the top | 69 | 11 | 32 |
| development set, functions in the top five files | 45 | 33 | 48 |
| development set, functions, no file list | 61 | 39 | 72 |

The first four rows are out of 280. The last three are out of 115. Hit@10 in a file row is a gold file. Every budget column is a gold function whose source fits.

A separate split is worth one number and no policy. Packing a function because the issue spells its name contains the edit on 23 of the 26 development tasks where a gold name appears, and on 25 of the 77 SWE-bench Lite tasks where one appears. Function ranking contains it on 11 and 42 of those same tasks. The position of the edit does not depend on this split. Rows are in `results/place.json`, `results/summary.json` and `results/gemma4/`.

## 4. Where this sits

File ranking from bug reports is an old result (Zhou, Zhang and Lo, 2012). Agentless asks a model to go from file to element to line (Xia et al., 2024). The step from the file to the function is partly available before the model runs, and it is not "read the file." On these two sets the function begins more than a thousand tokens into the file that retrieval already got right. RepoGraph and GraphLocator use a graph as something a model can navigate after a seed exists (Ouyang et al., 2025; Liu et al., 2026). The seed this note can defend is the span, not the call that leaves it.

## 5. Limits

Gemma was not run, so a function in context is not a passing patch. The development texts are the public pull requests, not the hidden test and not a byte copy of the competition file. Module-level edits are outside the counts. A pure insertion can be charged to a neighbor. Another tokenizer would move the medians. It would move the prefix and the packed spans by the same rule. The claim is that the edit sits past the prefix, and that packing the functions in a file that is already known recovers part of that gap and not all of it.

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

Jha, H. K. Gemma 4 graph-retrieval benchmark. Hugging Face dataset, 2026.
