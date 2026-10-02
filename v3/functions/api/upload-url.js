export async function onRequestPost(context){try{const body=await context.request.json();if(!body.name||!body.size)return new Response("Invalid file", {status:400});if(body.size>200*1024*1024)return new Response("200 MB maximum", {status:413});
const key="uploads/"+crypto.randomUUID()+"-"+body.name.replace(/[^A-Za-z0-9._-]/g,"_");
// This endpoint intentionally returns configuration status until an R2 S3 presigner is bound.
// Browser-to-storage upload avoids routing the file body through Streamlit.
return Response.json({configured:false,key,message:"Bind R2/S3 presigned-upload service to activate direct upload."},{status:503});
}catch(e){return new Response(String(e),{status:500})}}