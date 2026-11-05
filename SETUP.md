# One-time setup

About 20 minutes. Meta moves its buttons around now and then, so labels may differ a little.

## 1. Make your Instagram a Creator account

Instagram app → **Settings and activity → Account type and tools → Switch to professional account → Creator.**

It's free and reversible. Instagram only lets professional accounts post through its API.

## 2. Create a Meta developer app

1. Go to <https://developers.facebook.com/apps> and log in with Facebook. Accept the developer terms if this is your first time.
2. **Create app**:
   - Name it something like *solgutt uploader*.
   - For the use case, pick **Manage messaging & content on Instagram**.
   - Skip the business portfolio.
   - Finish creating.
3. In the app, open **Use cases → Customize** (next to the Instagram use case). Under **Permissions**, make sure **`instagram_business_content_publish`** is added, along with `instagram_business_basic`.

The app can stay in **Development** mode. You don't need App Review to post to your own account.

## 3. Generate the access token

1. Still in the Instagram use case, open **API setup with Instagram login → Generate access tokens → Add account.** Log in to your Instagram account.
   - If it asks for a tester role: go to **App roles → Roles → Add people → Instagram Tester** and enter your username. Then accept the invite in the Instagram app: **Settings → Website permissions → Apps and websites → Tester invites**.
2. Click **Generate token** and copy it. It's a long string starting with `IG…`.

## 4. Store the token in GitHub

Repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret**

- Name: `IG_ACCESS_TOKEN`
- Value: paste the token.

## 5. Let the token renew itself

Instagram tokens expire after 60 days. The weekly refresh job renews them, but it needs permission to update the secret:

1. Go to <https://github.com/settings/personal-access-tokens/new> and create a **fine-grained token**:
   - Repository access: **Only select repositories →** `instagram-uploader`
   - Permissions: **Secrets → Read and write**
   - Expiration: the longest allowed. GitHub emails you before it expires.
2. Add it as a second repository secret named **`GH_PAT`**.

If you skip this step, everything still works, but you'll have to repeat step 3 every ~60 days.

## 6. Test it

GitHub → **Actions → Post to Instagram → Run workflow.**

1. Leave **dry run** ticked and run it. The log shows which photo and caption would go out, and confirms Instagram can reach the image.
2. When that looks right, run it again with **force** ticked and **dry run** unticked. This posts the next photo for real.

From then on it runs by itself. GitHub emails you if a run ever fails, for example when the token expires.
