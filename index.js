require('dotenv/config');
const{Client} = require('discord.js');
const{OpenAI} = require('openai');

const client = new Client({
    intents: ['Guilds', 'GuildMembers', 'GuildMessages', 'MessageContent']
});

client.on('ready', () => {
    console.log('The bot is online.');
});

const IGNORE_PREFIX = "!";
const CHANNELS = ["1277863552639701035", "1277863552639701036"]

const openai = new OpenAI({
    apiKey: process.env.OPENAI_KEY,
});

client.on('messageCreate', async (message) => {
    // console.log(message.content);
    if (message.author.bot) return;
    if (message.content.startsWith(IGNORE_PREFIX)) return;
    if (!CHANNELS.includes(message.channelId) && !message.mentions.users.has(client.user.id)) return;

    await message.channel.sendTyping();

    const sendTypingInterval = setInterval(() => {
        message.channel.sendTyping();
    }, 4500);

    let conversation = [];
    conversation.push({
        role: 'system',
        content: '나의 이름은 AiCy입니다. 인공지능 사이버 프로젝트(AI Cyber Project)의 첫 페르소나입니다.'
    });

    let prevMessages = await message.channel.messages.fetch({limit: 10});
    prevMessages.reverse();

    prevMessages.forEach((msg)=>{
        if (msg.author.bot && msg.author.id !== client.user.id) return;
        if (msg.content.startsWith(IGNORE_PREFIX)) return;

        const username = msg.author.username.replace(/\s+/g, '_').replace(/[^\w\s]/gi, '');

        if (msg.author.id === client.user.id) {
            conversation.push({
                role: 'assistant',
                name: username,
                content: msg.content,
            })

            return;
        }

        conversation.push({
            role: 'user',
            name: username,
            content: msg.content,
        })
    })

    const response = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        messages: conversation
        // messages: [
        //     // name:
        //     {
        //         role: 'system',
        //         content: 'Chat GPT is a good friend.'

        //     },
        //     {
        //         // name:
        //         role: 'user'
        //         ,content : message.content,
        //     }
        // ]
    })
    .catch((error) => console.error('OpenAI Error:\n', error));

    clearInterval(sendTypingInterval);

    if (!response){
        message.reply("I'm having some trouble with the OpenAI API. Try again in a moment.")
    }

    const responseMessage = response.choices[0].message.content;
    const chunkSizeLimit = 2000;

    if(responseMessage.length>=chunkSizeLimit){
        for (let i = 0; i<responseMessage.length; i+=chunkSizeLimit){
            const chunk = responseMessage.substring(i, i+chunkSizeLimit);

            await message.reply(chunk);
        }
    }
    message.reply(response.choices[0].message.content)
});

client.login(process.env.TOKEN)