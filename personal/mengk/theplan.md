> What kind of object should Docent be? How should it interface with other things?

<!-- It feels time to reconsider Docent's identity. What is it supposed to be? What end does it serve? -->

Despite shipping a couple versions of Docent by now, we haven't been very opinionated about what Docent *actually* is: is it [x, y, z]?. As a result, Docent has somewhat of an amorphous shape; you can see glimpses of utility everywhere, but nothing is fully realized.

It's important that we understand the entire space of possibilities, so I'm glad we invested time there, but we should sharpen our goals.

I’m seeing several types of end-goals from Docent users:
* **Open-ended exploration**: Building a judge is a good way of exploring a fuzzy space you don’t yet understand. Some users may not have thought past this step, and just want to learn something interesting.
    * **What they want**: They generally reach for basic data analysis: find examples of a behavior, cluster them, click through some examples, plot some numbers against each other. They ask a wide variety of questions, from "why is my agent failing?" to "classify reward hacking" to “how should I improve the prompt?” Accuracy is nice but not their foremost concern. Their engagement with Docent begins and ends in the UI. They don’t usually reach for programmatic control, hackability, or exportability.
    * **Example users**: misc MATS scholars,
    * **How well Docent works for them**: Already works pretty well. Important next-step  Once we 1) support flexible system prompts and output schemas and 2) polish the detailed review flow, these users can simply tell the refinement agent what they want, click around the UI, and massage the prompt until they get something they like. It’ll be good.
    * We’ve (somewhat unconsciously?) optimized Docent a lot for this use-case (frankly, we didn’t deeply see other possibilities until recently), so it makes sense that most engaged users are in this camp. But we don’t want to stay here forever – our tool will be more nice-to-have than critical. If we can close the loop from analysis to action, we’ll become a lot stickier. How do we get there?
* **Building automated judges for _assisting_ evaluation**: The difference between this and having the judge _perform_ evaluation is that, here, users do careful review
    * **METR case study**: In their GPT-5 task horizon paper, METR reported several results involving LLM monitors: [x, y, z]. I saw lots of places where better tooling should've made the process more efficient, correct, and transparent -- but when I put myself in the shoes of a METR researcher, it was clear why Docent doesn't (yet) solve their problems.

        Here's how I'd summarize their LLM judging workflow (* = only done sometimes):
        1. Create an LLM monitor for the behavior of interest by choosing some prompt x model x etc combination.
        2. (*) Download an internal pre-made dataset that evaluates classifiers for that behavior, though the transcripts might be drawn from a different data dist.
        3. (*) Iterate that monitor against the dataset.
        4. Run it against real data.
        5. Manually review real results before publishing them in a chart or describing the matching samples. It's unclear how thorough this review is; sometimes it sounded very thorough, but other times not so much. (I remember one case where they looked through ~50 things?)

        Imagine what a METR researcher would think about Docent:
        > _Okay, I just ran steps 1-3 in a Jupyter notebook. Now what? My judge is just some Python function that calls OpenAI's API with some sampling parameters and a system prompt; I can't stick that into Docent. Also, there's no labeling or annotation functionality - I need a place to track that. If I then wanted to run the finalized judge on more stuff, I also couldn't do that. What is Docent even supposed to help with?_

        Here's what I see as Docent's primary value proposition:
        * Without a dedicated UI, it's very painful to review judge outputs for long transcripts.
        * We can significantly speed-up the loop between (1) notice issue with judge outputs, (2) note that with a label, (3) iterate on the prompt, and (4) see if that helped.
        * Essentially, most gains are in having a UI to review outputs and iterate on the judge quickly.

        If I were the METR researcher, here's what I might want:
        * Docent provides a judging library in Python. It exposes every knob I could want to tune. It's also just a thin wrapper around calling the OpenAI/Anthropic/etc SDKs locally, so I have full control over backoffs, API keys, etc. That is, if I'm calling the Judge SDK, Docent is not responsible for infrastructure.

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
                judge(agent_run)
            ```

        * I can run steps 1-3 using Docent's judging library while customizing whatever I want.
        * I can push the current judge to the server with `dj.push()`, then view it in Docent.
        * After I finish iterating on it with Docent, I can download the judge and continue running whatever I want through it.

            ```python
            judge.pull()
            # OR
            judges = dj.list_judges(collection_id="...")[i]
            # OR
            judge = dj.get_judge(judge_id="...")

            # Then run the judge on whatever
            judge(agent_run)
            ```

        * The `docent` package auto-traces the judge, along with agent runs. For example:

            ```python
            from docent.trace import agent_run

            @agent_run
            def my_agent():
                outputs = run_agent()
                reward = judge()
            ```

            logs agent runs directly back into Docent, meaning we now have more data to label! This could support a sort of continual learning workflow.

Small detail: how are users supposed to "format agent runs" into the right format?

There is a bet we are making here, which is that the value we can provide with Docent _outweighs_ the limitations of using our framework. It won't be as straightforward to hack your judges in various cursed ways, but we should also make sure to support lots of things ergonomically: e.g., pairwise comparison judges, sampling many times to reduce variance. (I think these are both possible.)
* You

One way I'd think about it is: judges are not programmed in code; they are programmed with the interactive exploration of data. Especially given that the _implementation details_ of judges are so simple, it makes sense that we prioritize the ease with which they can be iterated on in the UI. (?)

Cursor's use-case:
-


* **Building automated judges for _evaluating_ behaviors**: To be clear, we distinguish _evaluating_ behaviors from _optimizing or iterating_ against them, because the workflows look quite different.
    * **What they want**:
* **Data labeling**: A user has a large dataset of agent runs and labeling signature `(agent_run) -> output_schema`; their goals are to (1) select the "most interesting" transcripts to label, then (2) manually produce one `output_schema`-typed object per agent run, quickly and accurately.
    * **What they want**:


Automated measurement for ev


As I'll discuss below, we've been catering heavily to the "exploration" crowd, which is natural. That's the mode we've been in, too:  But exploration is almost always a means to an end, and if we want Docent to "stick" as a product, we should attempt to bridge the gap from analysis to action.
