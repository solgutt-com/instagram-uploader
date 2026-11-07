# One-time setup (already done for @sol_gutt_foto)

This is the route that worked in November 2026. Meta changes its screens often.

## 1. Professional account
**@sol_gutt_foto** must be a **Creator** or **Business** account: Instagram app → Settings → Account type and tools.

## 2. Meta app
At developers.facebook.com there's an app called **SolGutt uploader**. Its use case is *Manage messaging & content on Instagram*, it's linked to a business portfolio, and it has a Unified-login configuration.

## 3. Token from a system user
At [business.facebook.com/settings](https://business.facebook.com/settings), inside the business portfolio:

1. **Accounts → Instagram accounts:** add `sol_gutt_foto`.
2. **Users → System users:** there's a system user named `uploader` (Admin).
3. **Assign assets:**
   - the app *SolGutt uploader*, with full control
   - `sol_gutt_foto`, with full control
4. **Generate token:**
   - App: *SolGutt uploader*
   - Expiration: **Never**
   - Permissions: `instagram_basic` and `instagram_content_publish`

   This gives a code starting with `EAA`. It never expires.

## 4. GitHub secrets
Add these at [repo → Settings → Secrets and variables → Actions](https://github.com/solgutt-com/instagram-uploader/settings/secrets/actions):

| Secret | Value |
|---|---|
| `IG_ACCESS_TOKEN` | the `EAA…` token |
| `IG_USER_ID` | @sol_gutt_foto's ID (Business Settings → Instagram accounts → sol_gutt_foto). Usually starts with 1784. |

Use the website form rather than the `gh secret set` command. With the command, it's easy to end up pasting the command itself instead of the token.

`config.json` has `"instagram_username": "sol_gutt_foto"`. If a token ever reaches a different account, the uploader refuses to post.

## 5. Test
GitHub → **Actions → Post to Instagram → Run workflow**, with **dry run** ticked.

The log should say `Token OK – connected to @sol_gutt_foto` and show the caption it would post.

## If the token is ever revoked
Generate a new one as in step 3, then update `IG_ACCESS_TOKEN`. The weekly *Refresh Instagram token* job does nothing for this kind of token, which is expected.

## 6. The Mac watcher
Run once:

```bash
bash ~/Desktop/solgutt.github.io/instagram-uploader/scripts/install-watcher.sh
```

Click **Allow** when macOS asks whether "Instagram Uploader" may access the Desktop folder.

## 7. Posting with the Mac off
*Set up on Nov 7, 2026: the job is "Instagram poster" on cron-job.org, and the GitHub key is "cron-job.org poster".*

[cron-job.org](https://cron-job.org) is free. It calls GitHub at your posting times and starts the posting job, so posts go out even when the Mac is off or asleep. GitHub's own timer is too unreliable for this.

**a. A GitHub key that can only start the posting job.** Go to [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new):
- Name: `cron-job.org poster`
- Expiration: the longest allowed. Set a reminder to renew it.
- Repository access: **Only select repositories →** `instagram-uploader`
- Permissions → **Actions: Read and write**. Nothing else.
- Click **Generate token** and copy it. It starts with `github_pat_`.

**b. The cron job.** Sign up at cron-job.org, then go to **Cronjobs → Create cronjob**:
- Title: `Instagram poster`
- URL: `https://api.github.com/repos/solgutt-com/instagram-uploader/actions/workflows/post.yml/dispatches`
- Schedule: **Custom**
  - Days: every day
  - Hours: `9` and `19`
  - Minutes: `2` and `32`
  - Time zone: `Asia/Jerusalem`

  That's 4 calls a day: 2 tries per posting time. A slot that's already posted is skipped, so the extra calls are harmless.
- **Advanced** tab:
  - Request method: **POST**
  - Headers:
    - `Authorization` = `Bearer github_pat_…`: the word `Bearer`, one space, then the key from step a, with no quotes
    - `Accept` = `application/vnd.github+json`
    - `X-GitHub-Api-Version` = `2022-11-28`
  - Request body: `{"ref":"main","inputs":{"dry_run":"false"}}`
- Save, then click **Test run**. A response of **204** means GitHub accepted it. The other codes mean:
  - **401**: the `Bearer ` part or the key is wrong
  - **403**: the key lacks *Actions: Read and write*
  - **404**: there's a typo in the URL, or the key has no access to `instagram-uploader`

**Renewing the key:** GitHub keys expire. Before it does, create a new one (step a) and paste it into the cron job's `Authorization` header. Nothing else changes.

If you change `post_times` in `config.json`, change the hours here too.
