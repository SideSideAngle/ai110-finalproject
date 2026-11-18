# 🎧 Model Card: SymphonySearch

## 1. Model Name  

Give your model a short, descriptive name.  
Example: **SymphonySearch 1.0**  

---

## 2. Intended Use  

Describe what your recommender is designed to do and who it is for. 
Designed to take in natural language search queries and provide personalized song recommendations

Prompts:  

- What kind of recommendations does it generate
Recommendations based on the user's search query  
- What assumptions does it make about the user  
The user wants to find and listen to specially chosen music
- Is this for real users or classroom exploration 
Real users 

---

## 3. How the Model Works  
Takes in search query from user, uses RAG to find matches in the knowledge points, builds a music profile using what was retrieved from RAG and the LLM's own reasoning to compute a confidence score which shows how confidence the system is in the created music profile matching with the search query. Then it uses the music profile to score every song in the data. Scores closest to the target scores in the profile get pooled and walked from best score to worst. Top 5 remain.


---

## 4. Data  

Describe the dataset the model uses.  

Prompts:  

- How many songs are in the catalog 
2700 from a Kaggle Dataset
- What genres or moods are represented  
Wide variety of genres
- Did you add or remove data 
Dataset had a lot more than 2700 so a split was made to keep 2700 songs, all of varying genreas and musical attributes
- Are there parts of musical taste missing in the dataset
Since this is meant to be a "all in one" tool which can be of use to any user, could be certain cases where a search does not provide a valuable list of songs for the user. 

---

## 5. Strengths  

Where does your system seem to work well  

Clear requests work well, results are explained, AI only parses and explains, no decisions. Bad inputs are handled.
Retrieval (RAG) works and shapes the results. 

---

## 6. Limitations and Bias 

Where the system struggles or behaves unfairly. 

Genre and mood take a lot of weight in scoring. 
Mood does not exist in the dataset, its computed using valence, energy, acousticness.
Genre labels are noisy. 
Skews towards more popular songs.
Retrieval matches words, not meaning.

---

## 7. Evaluation  

How you checked whether the recommender behaved as expected. 

Prompts:  

- Which user profiles you tested  
variety of user profiles like game character personalities and different situations
- What you looked for in the recommendations 
Did the top 5 fit the request? Did the confidence make sense? Did bad input fail safely instead of crashing? Did retries show new songs and respond to the note? Were the top 5 spread across artists? 
- What surprised you  
nothing really checks whether the confidence is really confidence that the profile is correct
The system never has to crash to be wrong
Fixing one thing broke another.


### What I tested
92 automated tests (all passing) covering the scorer, bad input, guardrails, retrieval, validation of LLM output, fallback when the LLM fails, retries, and the web app driven headlessly.
27 golden cases run by eval/run_eval.py in offline mode: direct profiles, natural-language requests, 5 guardrail attacks (empty, gibberish, over-long, prompt-injection-style, vague), and 3 follow-up retries.
Human ratings (thumbs up/down and "what was off?") logged during real use. There are only 5 so far (2 positive), all from me, so they show the loop works but prove nothing yet.

### Why does "Gym Hero" keep showing up for people who just want Happy Pop?


### Comparing the profiles side by side



---

## 8. Future Work  

Ideas for how you would improve the model next.  

Prompts:  

- Additional features or preferences  
- Better ways to explain recommendations  
- Improving diversity among the top results  
- Handling more complex user tastes  

better scoring algorithm to handle more cases
confidence checker
tune against real data
additional refinements

---

## 9. Personal Reflection  

A few sentences about your experience.  

Prompts:  

- What you learned about recommender systems  
way more complicated than you would think for things we use everyday. way more goes into them than we realize. 
- Something unexpected or interesting you discovered  
was super interesting to see how the recommendation itself works but also how the whole pipline fits and works together
- How this changed the way you think about music recommendation apps  
translating human desire into recommendations takes a lot of data, time, and technique
