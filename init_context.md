We have an app that can create personalized agents which can have a knowledge base, tools to connect to external apps and personalized instructions. Our system is quite manual but we can integrate with telegram, instagram, whatsapp, messenger, chatbot, web landing, slack, teams, discord, API. We also have other features such as workflow automation with agents, databases for agents (for users that struggle with ERPs or CRMs).

In this app we created at the beginning the expert type agent, which was a personalized agent capable of absorving different types of files and create its own knowledge base, but the framework was too powerful for the usage cases we had. We will opensource it.

The framework live shere: /Users/bgg/Documents/repos/nirvana/nirvanav0/backend_ml_cpu/agents/nirvana_agents/utilities/graphrag

Graphrag base logic:
- LLMs to extract entities and relashionshipts via specialized system prompts and formats, for local search
- LLMs extract communities for global search based on the separation and entities
- Define short descriptions of the entities and encode with embedding models
- Construct parquet files with communities, entities and relashionships tracking, we can create a graph file constructing it via the parquet
- For queries in global search it matches the query with the communities and description of these, extracts the top X and then builds a prompt for final answer with a LLM, but the search method returns the context, for local queries it uses the description of the entities and extract entities as well as relationships linked to that entity
- Uses vectorstores to calculate distances

The framework is based on graphrag but we made many improvements:
- We added leiden algorithm to be able to update relationships in the knwoledge base without having to re-create entirely again. Also we added a bit of NLP to understand which entitnes are closer based on the description of it.
- We improved the dataframe classes to be able to track the original files and have an edition and deletion process per file instead of worrying about tracking chunks separately.
- We added sources relationships, mantaining the original source of the chunk the final answer directly cites the original file in the answer.
- We create config files to add personalization.
- We added agentic logics to be able to work with excel files, vision models for images, etc. Instead of using multimodal embedding we can simply extract entities and relationships from the source.
- We improved prompt engineering logic to extract entities and relationships properly.
- We added the search methods logic.
- In order to use a wider range of models we improve prompts, preprocessing and have ai logics to implement fixes instead of a simple python logic.
- We implemented personalized entities with ai to create 

By doing these changes we were actually worried of making it work with our agentic logic instead of generalizing, in this case since we want to opensource this new library we will need to make tons of changes as well as improvements.

Some observations:
- Since the library was created to be adapted to our agentic logic we have some exceptions. The agentic logic cannot be used this is propietary, the rest of the logics inside the graphragder as well as the vectorstores can be migrated to a better opensource library. The storage works with s3 and is not personalized, we need to migrate the files in order to make it 100% locally, define paths, have command lines. There are some parameters that might not be needed other that still might be useful like the session.
- The current logic uses achain_nirvana which is propietary but is basically and LLM wrapper, so in the llm_wrapper of the logic we need to implement normal use of openai libary so it can be adapted to different worklows. We can apply a normal error handling and we do need to implement caching smart, the base_nirvana_chains explain this which works with sessions ideally.
- We need to improve a lot the personalization of paths in local and cloud options, the outputs generated and where these are generated, we need to implement testing and tracking of different processes to understand costs and others. We need to hav e benchmarks so later in another session we will be creating a simple case to at least evaluate that, this will happen once everything else is ready sicne it should be one of the last commands, the user will be able to create its own datasset and then use it to make. beautiful report.
- We will make tons of improvements and different searches commands for set up, different algorithms, incremental requirements, skills for agents, etc, so you understand what we want to achieve but first we need to focus on the migration.
- We need to adjust a lot of the logic but we do have an incredible starting point partner.
- Some parameter personalization live only in the code whlie it should a folder spehis that we will accompny with md docuemntation for each module.
- There is nirvana branding we need to change this to grail which will be the official name
- We will be adding a re-ranker addition which would be optional, many settings could be optional.
- We need to create a lot of code documentation, we will work on a general documentation with docusaurus in another repo but for now the code should still have commentaries, in the main files we would mention Nirvai (nirvana) like "Provided by Nirvai, Author: Benjamin González Guerrero"
- The library needs a lot of standarazing, the working logic is quite powerful but in order to make it opensource we need to make it better.

First we will start by analizing all necessary files and creating a CLAUDE.md in this repo which needs to be initilazed like:
git remote add origin git@github.com:CAMARA-CHILENA-INTELIGENCIA-ARTIFICIAL/GRAIL.git
git branch -M master
git push -u origin master

That will contain all the roadmap, the logics documented, the context needed for any type of process, important files, schemas, warning, migration needs etc. Initialize the repo and then analyze ALL the necessary files from the opriginal source and start creating the prompt containing the full implementaiton needed to achieve this. You can copy the files needed to the repo if need or analyze directly, we will start with this context and prompt, in other sessions we wil take care of making the actual changes.