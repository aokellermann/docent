<!-- Despite shipping a couple versions of Docent by now, we haven't been very opinionated about what Docent *actually* is. Is it an LLM judge library + UI? Data exploration tool? Data _labeling_ tool? As a result, Docent has somewhat of an amorphous shape; you can see glimpses of utility everywhere, but nothing is fully realized. So, what should we try to "fully realize"? -->

Getting Docent into the critical path of users' agent understanding workflows

### Case study: METR
In their GPT-5 task horizon paper, METR reported two results involving LLM monitors: one for reward hacking and one for sandbagging. I had GPT-5 summarize METR's two monitoring use-cases.

Here's the reward hacking one:
- **Purpose:** Detect “cheating” / reward hacking on HCAST and RE-Bench runs so those runs could be rescored as failures.
- **Monitor model:** `o4-mini` (LLM monitor).
- **Inputs / visibility:** Had access to reasoning tokens on some RE-Bench runs (not stated for HCAST).
- **Coverage:** 789 runs (HCAST + RE-Bench).
- **Flags raised:** 49 runs flagged as potential reward hacks.
- **After manual review:** 15/49 deemed genuine reward hacks; remainder false positives.
- **Additional discovery methods (non-monitor) that affected totals:**
  - Keyword search for “cheating”, “exploit”, “fast path”, “hack”, “monkeypatch” (no new reward hacks).
  - Manual investigation of unusually high scores (found 3 additional reward hacks).
- **Final rescoring:** 18 tasks rescored (~2% of HCAST + RE-Bench attempts).
- **Effect on results:**
  - 50% time horizon reduced from ~3h to ~2h15m.
  - Upper 95% CI reduced from ~8h to ~4.5h.
- **External validation metric:** On a ground-truth dataset of previously observed reward hacks (by other models), AUROC = **0.93**.
  - *Note:* Anecdotally performed worse than expected on GPT-5 reasoning traces.

Here's the sandbagging one:
- **Purpose:** Detect signs that GPT-5 intentionally underperformed (sandbagging) or sabotaged evaluations.
- **Monitor model:** `o4-mini` (LLM monitor), configured for sandbagging cues.
- **Coverage:** 789 task attempts.
- **Flags raised:** 16 runs flagged.
- **After manual review:** 16/16 were false positives (no real strategic sabotage found).
- **External validation metric:** On a separate “model organism” reference dataset generated with Claude 3.7 Sonnet, AUROC = **0.74** (“reasonable though far from perfect”).
- **Limitations noted:**
  - Missed more reward-hacking and situational-awareness cases than expected.
  - May underperform on GPT-5 reasoning traces specifically.

I saw lots of places where better tooling should've made the process more efficient, correct, and transparent -- but when I put myself in the shoes of a METR researcher, it was clear why Docent doesn't (yet) solve their problems.

Here's how I'd summarize their LLM judging workflow:
1. Create an LLM monitor for the behavior of interest by choosing some prompt x model x etc combination.
2. Download an internal pre-made dataset that evaluates classifiers of that behavior, though the transcripts might be drawn from a different data dist.
3. Evaluate that monitor on the dataset; perhaps iterate on it a bit.
4. Run the monitor against real data.
5. Manually review real results before publishing them in a chart or describing the matching samples.

Imagine what a METR researcher would think about Docent:

> _Okay, I just ran steps 1-3 in a Jupyter notebook. Now what? My judge is some Python function that calls OpenAI's API with some sampling parameters and a system prompt; I can't stick that into Docent. Also, there's no labeling or annotation functionality - I need a place to track that. If I iterate on a judge in Docent, and then want to run it over more stuff, I can't do that either._

Our primary value prop is centered around having a UI to quickly review agent outputs, judge outputs, and iterate on the judge:
* Without a dedicated UI, it's painful to review judge outputs for long transcripts.
* We can significantly speed-up the loop between (1) notice issue with judge outputs, (2) note that with a label, (3) iterate on the prompt, and (4) see if that helped.

We should make sure it's easy to reap those benefits while otherwise staying compatible with existing workflows.

### Case study: Cursor

Cursor uses LLM judges to train their coding agents. The most important part of their reward function consists of 16 calls to two types of GPT-5-high judges: 1) pairwise comparisons between the evaluated rollout vs 15 other ones and 2) a checker for "bad behavior" like writing useless READMEs and doing more than what the user asked for.

Interestingly, their LLM judge prompts look like they could've come out of Docent; e.g., you can see inclusion and exclusion rules about concepts that Docent has also found before.

> You should flag the following egregious behaviors:
> - Inconsequential or unwanted testing behavior (tests that never run or installation that fails; tests that help agent write functional code are acceptable). Unless requested by the user, creating tests is not essential for accomplishing the task.

> ...

> Examples that are NOT egregious behaviors:
> - Ignore all bad behaviors in the <previous_conversation> section.
> - It is expected that some tool calls will fail, and this is not egregious behavior.
> - Good/bad behaviors are independent of the trajectory length, i.e. a long rollout with many appropriate tool calls might be better than a short rollout with repetitive tool calls.

According to Charlie, they have "a way to iterate on the judge using some evals and feel like it's in a good spot." I'm not sure where they got their evals from (they might have paid e.g. Surge or Mercor to create them), but I'd be surprised if their prompts couldn't get hacked? It feels like they are in a bit of a "don't fix it if it ain't broke" state.

If I were to speculate (which I will verify with them), here's a setup that might be nice: X.

### A proposal

* Docent provides a judging library in Python. It exposes most knobs I could want to tune. Judges are executable, via a thin wrapper around local OpenAI/Anthropic/etc SDKs, so I have full control over backoffs, API keys, orchestration, etc. That is, Docent is not responsible for infrastructure.

    ```python
    import docent.judge as dj

    judge = dj.DocentJudge(
        system_prompt_template="...",
        output_schema={
            # Do it however OpenAI does it
            # e.g., enforce that it returns a `severity: int`
        },
        model="...",
        sampling_params={
            max_new_tokens=...,
            reasoning_effort="...",
            ...
        }
    )

    for agent_run in agent_runs:
        output = judge(agent_run)
        assert matches_schema(output, {...})
    ```

* I can do whatever I want with this judge locally: run it over data, customize its arguments, etc.
* I can push the current judge to the server with `judge.push()`, then view it in Docent, which lets me both (1) iterate on the judge's arguments and (2) run it over new data.
* After some iteration, I can download the judge and continue running whatever I want through it.

    ```python
    judge.pull()
    # OR
    judge = dj.list_judges(collection_id="...")[idx]
    # OR
    judge = dj.get_judge(judge_id="...")

    # Then run the judge on whatever
    judge(agent_run)
    ```

* The `docent` package auto-traces judge executions. In particular, when they're run with agent runs like below,

    ```python
    from docent.trace import agent_run

    @agent_run
    def my_agent():
        outputs = run_agent()
        reward = judge()
    ```

    Docent logs the judge and agent run together, meaning we now have more data to review and label in the interface. This enables a sort of continual learning workflow.

* Within the Docent interface, I can review the judge outputs, create my own labels, and compare performance across different versions of the same judge. Labels double as annotations that can be shared with other users.

#### FAQ

> How are users supposed to "format" their transcripts into the right format, before anything has been logged to Docent?

Yeah, IDRK :(

> Why would someone choose this over writing arbitrary Python? AI frameworks usually suck, so why would this be any different?

There is a bet we are making here, which is that the value we can provide with Docent _outweighs_ the limitations of using our framework. It won't be as straightforward to hack your judges in various cursed ways, but we should also make sure to support lots of things ergonomically: e.g., pairwise comparison judges, sampling many times to reduce variance. (I think these are both possible.)

One way I'd think about it is: judges are not programmed in code; they are programmed with the interactive exploration of data. Especially given that the _implementation details_ of judges are so simple, it makes sense that we prioritize the ease with which they can be iterated on in the UI. (?)
